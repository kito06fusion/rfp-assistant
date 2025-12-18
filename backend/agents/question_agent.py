from __future__ import annotations

import json
import logging
import re
from typing import List, Dict, Any, Optional

from backend.llm.client import chat_completion
from backend.models import RequirementItem, Question, BuildQuery, RequirementsResult
from backend.rag import RAGSystem
from backend.knowledge_base.company_kb import CompanyKnowledgeBase
from backend.agents.prompts import QUESTION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
QUESTION_MODEL = "gpt-5-chat"


def _build_rag_context_for_requirement(
    requirement: RequirementItem,
    rag_system: Optional[RAGSystem],
    max_chunks: int = 3,
) -> str:
    if rag_system is None:
        return ""

    try:
        search_query = requirement.source_text
        logger.info(
            "Question agent: running RAG search for requirement %s (k=%d, query_len=%d)",
            requirement.id,
            max_chunks,
            len(search_query),
        )
        results = rag_system.search(search_query, k=max_chunks)
        logger.info(
            "Question agent: RAG search for requirement %s returned %d chunk(s)",
            requirement.id,
            len(results),
        )
        if not results:
            return ""

        parts = [
            "RAG CONTEXT (PRIOR RFP ANSWERS / KNOWLEDGE ALREADY AVAILABLE):",
            "Use this ONLY to identify information that is ALREADY KNOWN so you DO NOT ask questions about it.",
            "If a detail clearly appears here, treat it as known and do NOT generate a question for it.",
            "",
        ]
        for i, r in enumerate(results, 1):
            chunk = r.get("chunk_text", "")
            if len(chunk) > 800:
                chunk = chunk[:800] + "..."
            parts.append(f"[RAG-{i}] {chunk}")
        return "\n".join(parts)
    except Exception as e:
        logger.warning("RAG lookup for requirement %s failed: %s", requirement.id, e)
        return ""


def _is_question_covered_by_rag(question_text: str, rag_context: str) -> bool:
    if not rag_context or not question_text:
        return False

    qt = question_text.lower()
    rc = rag_context.lower()

    words = [w for w in re.findall(r"\w+", qt) if len(w) > 4]
    if not words:
        return False

    overlap = sum(1 for w in words if w in rc)
    return overlap >= 2


def generate_questions(
    requirement: RequirementItem,
    all_requirements: List[RequirementItem],
    company_kb: CompanyKnowledgeBase,
    rag_system: Optional[RAGSystem] = None,
) -> List[Dict[str, Any]]:
    logger.info(
        "Question agent: analyzing requirement %s for information gaps",
        requirement.id,
    )
    
    known_topics = company_kb.get_all_known_topics()
    known_info_text = company_kb.format_for_prompt()
    rag_context = _build_rag_context_for_requirement(requirement, rag_system)
    
    all_req_text = "\n\n".join([
        f"[{req.id}] {req.source_text}"
        for req in all_requirements[:10]
    ])
    
    user_prompt = f"""Analyze the following requirement and identify ONLY the information that is MISSING or UNCLEAR that would be absolutely critical to create a proper response.

KNOWN COMPANY INFORMATION (DO NOT ask about these):
{known_info_text}

RAG CONTEXT (PRIOR RFP ANSWERS - TREAT THESE AS KNOWN INFORMATION):
{rag_context or "[No RAG context available for this requirement]"}

REQUIREMENT TO ANALYZE:
[{requirement.id}] {requirement.source_text}

CONTEXT FROM OTHER REQUIREMENTS:
{all_req_text}

TASK:
1. Identify information gaps in the requirement, but ONLY those gaps where missing information would materially harm the quality, correctness, or credibility of the final response.
2. Check if information is in the known company info (if yes, don't ask)
3. Generate specific, clear questions for ONLY the most critical missing information (it is better to ask zero questions than to ask marginal ones).
4. Prioritize questions by importance, marking only truly essential questions as "high" priority.

Output JSON array of questions, each with:
- question_text: string (the question)
- context: string (why this is important)
- category: string (technical, business, implementation, timeline, etc.)
- priority: string ("high", "medium", or "low")

If no questions are needed (all information is clear, in knowledge base, or any gaps are minor/nice-to-have), return an empty array [].
"""
    
    try:
        content = chat_completion(
            model=QUESTION_MODEL,
            messages=[
                {"role": "system", "content": QUESTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=1500,
        )
        
        cleaned = content.replace("```json", "").replace("```", "").strip()
        try:
            questions = json.loads(cleaned)
        except json.JSONDecodeError:
            import re
            array_match = re.search(r'\[.*\]', cleaned, re.DOTALL)
            if array_match:
                questions = json.loads(array_match.group(0))
            else:
                logger.warning("Could not parse questions JSON, returning empty list")
                questions = []
        
        if not isinstance(questions, list):
            questions = []
        
        validated_questions = []
        for q in questions:
            if isinstance(q, dict) and "question_text" in q:
                validated_q = {
                    "question_text": q.get("question_text", ""),
                    "context": q.get("context", ""),
                    "category": q.get("category", "general"),
                    "priority": q.get("priority", "medium"),
                }
                if validated_q["question_text"]:
                    validated_questions.append(validated_q)
        
        rag_filtered_questions: List[Dict[str, Any]] = []
        for q in validated_questions:
            if rag_context and _is_question_covered_by_rag(q["question_text"], rag_context):
                logger.info(
                    "Question agent: skipping question for requirement %s because RAG already covers it: %s",
                    requirement.id,
                    q["question_text"][:150].replace("\n", " "),
                )
                continue
            rag_filtered_questions.append(q)
        
        filtered_questions = []
        for q in rag_filtered_questions:
            question_text = q["question_text"].lower()
            should_skip = False
            for topic in known_topics:
                if topic.lower() in question_text:
                    if company_kb.has_info(topic):
                        logger.debug("Skipping question about known topic: %s", topic)
                        should_skip = True
                        break
            if not should_skip:
                filtered_questions.append(q)
        
        priority_order = {"high": 0, "medium": 1, "low": 2}
        filtered_questions.sort(key=lambda q: priority_order.get(q.get("priority", "medium"), 1))

        high_only = [q for q in filtered_questions if q.get("priority", "medium") == "high"]
        if high_only:
            selected = high_only[:2]
        else:
            selected = filtered_questions[:1] if filtered_questions else []

        logger.info(
            "Question agent: generated %d questions (validated=%d, rag_filtered=%d, final_selected=%d)",
            len(selected),
            len(validated_questions),
            len(rag_filtered_questions),
            len(selected),
        )
        
        return selected
        
    except Exception as e:
        logger.error("Question generation failed: %s", e)
        logger.exception("Full traceback:")
        return []


def analyze_build_query_for_questions(
    build_query: BuildQuery,
    requirements_result: RequirementsResult,
    company_kb: CompanyKnowledgeBase,
    max_questions_per_requirement: int = 3,
    rag_system: Optional[RAGSystem] = None,
) -> tuple[List[Dict[str, Any]], Dict[str, str]]:
    logger.info("Analyzing requirements individually for information gaps")
    
    known_info_text = company_kb.format_for_prompt()
    
    all_questions: List[Dict[str, Any]] = []
    rag_contexts_by_req: Dict[str, str] = {}
    
    for req in requirements_result.solution_requirements:
        logger.info("Analyzing requirement %s for information gaps", req.id)
        
        other_reqs_text = "\n".join([
            f"[{r.id}] {r.source_text}"
            for r in requirements_result.solution_requirements
            if r.id != req.id
        ])
        
        rag_context = _build_rag_context_for_requirement(req, rag_system)
        if rag_context:
            rag_contexts_by_req[req.id] = rag_context

        user_prompt = f"""Analyze this RFP requirement and identify what information the VENDOR needs to provide about THEIR SOLUTION to create a complete response.

REQUIREMENT TO ANALYZE:
ID: {req.id}
Type: {req.type}
Category: {req.category}
Requirement Text: {req.source_text}

CONTEXT - OTHER REQUIREMENTS (for reference):
{other_reqs_text[:1000] if len(other_reqs_text) > 1000 else other_reqs_text}

RESPONSE STRUCTURE REQUIREMENTS (how to format the response):
{build_query.response_structure_requirements_summary[:500]}

KNOWN COMPANY INFORMATION (DO NOT ask about these):
{known_info_text}

RAG CONTEXT (PRIOR RFP ANSWERS / KNOWLEDGE ALREADY AVAILABLE):
{rag_context or "[No RAG context available for this requirement]"}

TASK:
You are helping a VENDOR create a response to this RFP requirement. The requirement is clear - it specifies what the buyer needs.

Your job is to identify what information the VENDOR needs to provide about THEIR SOLUTION to answer this requirement completely.

CRITICAL: If the requirement EXPECTS or ASKS FOR specific information (e.g., "provide team structure", "include resourcing numbers", "list certifications", "describe previous projects", "specify timelines", "detail implementation approach"), you MUST ask the vendor about that information. Do NOT assume the LLM can make up this information - it must come from the vendor.

IMPORTANT:
- DO NOT ask questions that seek to clarify what the RFP requires (e.g., "What does the RFP mean by X?")
- DO ask questions about what the VENDOR can provide/offer/commit to (e.g., "What does your solution provide for X?")
- **If the requirement asks for specific information (team structure, resourcing, certifications, previous projects, timelines, etc.), you MUST ask the vendor about that information - the LLM cannot make this up.**
- Frame questions as asking about the vendor's solution, capabilities, offerings, or commitments
- Questions should help the vendor describe their solution in response to the requirement

Examples:
- If requirement mentions "SLA monitoring" → Ask: "What SLA metrics does your solution support for monitoring?" (NOT "What SLA metrics does the RFP require?")
- If requirement mentions "internal and external users" → Ask: "How many concurrent users can your platform support?" (NOT "How many internal and external users does the RFP specify?")
- If requirement mentions "integration" → Ask: "What integration capabilities does your solution provide?" (NOT "What systems need to integrate according to the RFP?")
- If requirement says "provide team structure" → Ask: "What team structure do you propose for this project? Include roles, responsibilities, and team size."
- If requirement says "include resourcing" → Ask: "What resourcing numbers and team composition do you propose for this project?"
- If requirement says "list certifications" → Ask: "What certifications does your organization hold that are relevant to this requirement?"
- If requirement says "describe previous projects" → Ask: "What previous projects or case studies can you provide that demonstrate your experience with similar requirements?"

Generate questions that will help the vendor provide concrete information about their solution in response to requirement {req.id}.

Output a JSON array of questions, each with:
- question_text: The question to ask the vendor about their solution (be clear and direct)
- context: Why this information is needed to create a complete response to requirement {req.id} (explain how it helps the vendor answer the requirement)
- category: Type (technical, business, implementation, commercial, timeline, resources, etc.)
- priority: "high" (critical for answering the requirement), "medium", or "low"

If all information needed to answer this requirement is already available in the knowledge base or the requirement is self-explanatory, return an empty array [].
"""
        
        try:
            response = chat_completion(
                model=QUESTION_MODEL,
                messages=[
                    {"role": "system", "content": QUESTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=1500,
            )
            
            questions = []
            try:
                response_text = response.strip()
                if response_text.startswith("```json"):
                    response_text = response_text[7:]
                if response_text.startswith("```"):
                    response_text = response_text[3:]
                if response_text.endswith("```"):
                    response_text = response_text[:-3]
                response_text = response_text.strip()
                
                parsed = json.loads(response_text)
                if isinstance(parsed, list):
                    questions = parsed
                elif isinstance(parsed, dict) and "questions" in parsed:
                    questions = parsed["questions"]
            except json.JSONDecodeError as e:
                logger.warning("Failed to parse questions JSON for requirement %s: %s", req.id, e)
                logger.debug("Response was: %s", response[:500])
                continue
            
            for q in questions:
                if isinstance(q, dict) and "question_text" in q:
                    q_text = q.get("question_text", "")
                    if rag_context and _is_question_covered_by_rag(q_text, rag_context):
                        logger.info(
                            "Question agent (build_query): skipping question for requirement %s because RAG already covers it: %s",
                            req.id,
                            q_text[:150].replace("\n", " "),
                        )
                        continue
                    validated_q = {
                        "question_text": q_text,
                        "context": q.get("context", ""),
                        "category": q.get("category", "general"),
                        "priority": q.get("priority", "medium"),
                        "requirement_id": req.id,
                    }
                    if validated_q["question_text"]:
                        all_questions.append(validated_q)
            
            req_questions = [q for q in all_questions if q.get("requirement_id") == req.id]
            if len(req_questions) > max_questions_per_requirement:
                priority_order = {"high": 0, "medium": 1, "low": 2}
                req_questions.sort(key=lambda q: priority_order.get(q.get("priority", "medium"), 1))
                excess = req_questions[max_questions_per_requirement:]
                for ex_q in excess:
                    all_questions.remove(ex_q)
            
            logger.info(
                "Generated %d questions for requirement %s",
                len([q for q in all_questions if q.get("requirement_id") == req.id]),
                req.id,
            )
            
        except Exception as e:
            logger.error("Question generation failed for requirement %s: %s", req.id, e)
            logger.exception("Full traceback:")
            continue
    
    filtered_questions = []
    known_topics = company_kb.get_all_known_topics()
    for q in all_questions:
        question_text = q["question_text"].lower()
        should_skip = False
        for topic in known_topics:
            if topic.lower() in question_text:
                if company_kb.has_info(topic):
                    logger.debug("Skipping question about known topic: %s", topic)
                    should_skip = True
                    break
        if not should_skip:
            filtered_questions.append(q)
    
    priority_order = {"high": 0, "medium": 1, "low": 2}
    filtered_questions.sort(key=lambda q: (
        priority_order.get(q.get("priority", "medium"), 1),
        q.get("requirement_id", ""),
    ))
    
    logger.info(
        "Generated %d total questions from %d requirements (filtered from %d)",
        len(filtered_questions),
        len(requirements_result.solution_requirements),
        len(all_questions),
    )
    
    return filtered_questions, rag_contexts_by_req


def analyze_build_query_for_questions_legacy(
    build_query: BuildQuery,
    company_kb: CompanyKnowledgeBase,
    max_questions: int = 20,
) -> List[Dict[str, Any]]:
    logger.info("Analyzing build query as whole (legacy mode)")
    
    known_info_text = company_kb.format_for_prompt()
    
    user_prompt = f"""Analyze this RFP build query and identify what information is MISSING or UNCLEAR that would be needed to generate a high-quality response.

BUILD QUERY:
{build_query.query_text}

KNOWN COMPANY INFORMATION (DO NOT ask about these):
{known_info_text}

Generate questions about information that is:
1. Missing from the build query
2. Unclear or ambiguous
3. Needed to create a proper, tailored response
4. Not available in the company knowledge base

Output a JSON array of questions, each with:
- question_text: The question to ask
- context: Why this information is needed
- category: Type (technical, business, implementation, commercial, etc.)
- priority: "high", "medium", or "low"
"""
    
    try:
        response = chat_completion(
            model=QUESTION_MODEL,
            messages=[
                {"role": "system", "content": QUESTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=2000,
        )
        
        questions = []
        try:
            response_text = response.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            parsed = json.loads(response_text)
            if isinstance(parsed, list):
                questions = parsed
            elif isinstance(parsed, dict) and "questions" in parsed:
                questions = parsed["questions"]
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse questions JSON: %s", e)
            return []
        
        validated_questions = []
        for q in questions:
            if isinstance(q, dict) and "question_text" in q:
                validated_q = {
                    "question_text": q.get("question_text", ""),
                    "context": q.get("context", ""),
                    "category": q.get("category", "general"),
                    "priority": q.get("priority", "medium"),
                }
                if validated_q["question_text"]:
                    validated_questions.append(validated_q)
        
        filtered_questions = []
        known_topics = company_kb.get_all_known_topics()
        for q in validated_questions:
            question_text = q["question_text"].lower()
            should_skip = False
            for topic in known_topics:
                if topic.lower() in question_text:
                    if company_kb.has_info(topic):
                        should_skip = True
                        break
            if not should_skip:
                filtered_questions.append(q)
        
        priority_order = {"high": 0, "medium": 1, "low": 2}
        filtered_questions.sort(key=lambda q: priority_order.get(q.get("priority", "medium"), 1))
        filtered_questions = filtered_questions[:max_questions]
        
        logger.info("Generated %d questions from build query (legacy mode)", len(filtered_questions))
        return filtered_questions
        
    except Exception as e:
        logger.error("Question generation from build query failed: %s", e)
        logger.exception("Full traceback:")
        return []


def analyze_requirements_for_questions(
    requirements: List[RequirementItem],
    company_kb: CompanyKnowledgeBase,
    max_questions_per_requirement: int = 2,
    rag_system: Optional[RAGSystem] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    all_questions = {}
    
    for req in requirements:
        questions = generate_questions(req, requirements, company_kb, rag_system=rag_system)
        questions = questions[:max_questions_per_requirement]
        all_questions[req.id] = questions
    
    total_questions = sum(len(qs) for qs in all_questions.values())
    logger.info(
        "Analyzed %d requirements, generated %d total questions",
        len(requirements),
        total_questions,
    )
    
    return all_questions


def infer_answered_questions_from_answer(
    answered_question: Question,
    answer_text: str,
    remaining_questions: List[Question],
) -> List[str]:
    if not remaining_questions or not answer_text.strip():
        return []

    logger.info(
        "Inferring additionally answered questions from answer to %s (remaining=%d)",
        answered_question.question_id,
        len(remaining_questions),
    )

    remaining_block = "\n".join(
        f"- ID: {q.question_id}\n  Text: {q.question_text}"
        for q in remaining_questions
    )

    system_prompt = (
        "You are helping to minimize redundant clarification questions for an RFP.\n"
        "When the vendor has answered one question, you check if that same answer "
        "also fully answers other pending questions.\n"
        "Only mark a question as answered if the provided answer gives a complete, "
        "usable answer for that question as written.\n"
        "If an answer only partially overlaps or you would still want a separate, "
        "focused answer, then DO NOT mark that question as answered."
    )

    user_prompt = f"""You are given:

1) The question that the vendor just answered
2) The vendor's answer text
3) A list of remaining open questions

Your task:
- Decide which of the remaining questions are now fully answered by the same answer text.
- Only select questions where, if you were the RFP author, you would accept that existing answer as a complete answer to that question.
- If a question would still benefit from its own specific answer, do NOT select it.

Return a JSON array of question_id strings. Example:
["REQ-01-q-0", "REQ-03-q-1"]

If none of the remaining questions are fully answered, return an empty array [].

JUST-ANSWERED QUESTION:
ID: {answered_question.question_id}
Text: {answered_question.question_text}

ANSWER TEXT:
{answer_text}

REMAINING OPEN QUESTIONS:
{remaining_block}
"""

    try:
        content = chat_completion(
            model=QUESTION_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=300,
        )

        cleaned = content.replace("```json", "").replace("```", "").strip()
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            import re

            array_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
            if array_match:
                result = json.loads(array_match.group(0))
            else:
                logger.warning(
                    "Could not parse inferred answered questions JSON, returning empty list"
                )
                return []

        if not isinstance(result, list):
            logger.warning(
                "Inferred answered questions result was not a list, got %s", type(result)
            )
            return []

        remaining_ids = {q.question_id for q in remaining_questions}
        inferred_ids = [
            qid for qid in result if isinstance(qid, str) and qid in remaining_ids
        ]

        logger.info(
            "Inferred %d additionally answered questions from LLM",
            len(inferred_ids),
        )
        return inferred_ids
    except Exception as e:
        logger.error("Inference of additionally answered questions failed: %s", e)
        logger.exception("Full traceback:")
        return []

