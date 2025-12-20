from __future__ import annotations

import json
import logging
import re
from typing import List, Dict, Any, Optional, Tuple

from backend.llm.client import chat_completion
from backend.models import RequirementItem, Question, BuildQuery, RequirementsResult, Answer
from backend.rag import RAGSystem
from backend.knowledge_base.company_kb import CompanyKnowledgeBase
from backend.agents.prompts import QUESTION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
QUESTION_MODEL = "gpt-5-chat"


# =============================================================================
# ITERATIVE QUESTION FLOW - One question at a time
# =============================================================================

def get_next_critical_question(
    requirements_result: RequirementsResult,
    company_kb: CompanyKnowledgeBase,
    rag_system: Optional[RAGSystem],
    previous_answers: List[Answer],
) -> Tuple[Optional[Dict[str, Any]], int]:
    """
    Get the next single critical question to ask.
    
    Flow:
    1. For each requirement, search RAG for existing info
    2. Identify what critical info is still missing (considering previous answers)
    3. Return ONE question for the most critical gap
    4. Returns (None, 0) when no more critical questions needed
    
    Returns:
        - question dict (or None if no more questions)
        - remaining_gaps_count
    """
    logger.info("Getting next critical question (previous_answers=%d)", len(previous_answers))
    
    known_info = company_kb.format_for_prompt()
    
    # Build context from previous answers
    answers_context = ""
    if previous_answers:
        answers_context = "\n".join([
            f"Q: {a.question_text}\nA: {a.answer_text}"
            for a in previous_answers
        ])
    
    # Gather RAG context for all requirements
    all_requirements_with_rag = []
    for req in requirements_result.solution_requirements:
        rag_ctx = _build_rag_context_for_requirement(req, rag_system, max_chunks=3)
        all_requirements_with_rag.append({
            "id": req.id,
            "text": req.source_text,
            "type": req.type,
            "rag_context": rag_ctx or "[No RAG info]",
        })
    
    requirements_text = "\n\n".join([
        f"REQUIREMENT {r['id']}:\n{r['text']}\n\nRAG INFO FOR {r['id']}:\n{r['rag_context']}"
        for r in all_requirements_with_rag
    ])
    
    user_prompt = f"""Analyze these RFP requirements and identify if there's any CRITICAL information missing that the vendor MUST provide.

KNOWN COMPANY INFO (available):
{known_info[:2000]}

PREVIOUS Q&A (info already gathered):
{answers_context or "[No previous answers yet]"}

REQUIREMENTS WITH RAG CONTEXT:
{requirements_text[:6000]}

TASK:
1. For each requirement, check if RAG context + known info + previous answers provide enough to write a credible response
2. Identify ONLY gaps where missing info would make the response WRONG or IMPOSSIBLE
3. Return the SINGLE most critical question (if any)

RULES FOR QUESTIONS:
- Question must be CONCISE - answerable in 3-5 sentences
- Ask about ONE specific thing, not multiple items
- Don't ask about info that's in RAG context or previous answers
- Don't ask generic questions - be specific to what's missing
- If a reasonable default answer would work, DON'T ask

OUTPUT FORMAT - Return JSON:
{{
  "has_critical_gap": true/false,
  "question": {{
    "question_text": "Concise, specific question (answerable in 3-5 sentences)",
    "context": "Brief reason why this is critical",
    "requirement_id": "REQ-XX",
    "category": "resources/timeline/technical/etc"
  }},
  "remaining_gaps": 0-N (estimate of other gaps after this one)
}}

If NO critical gaps exist, return:
{{
  "has_critical_gap": false,
  "question": null,
  "remaining_gaps": 0
}}
"""

    try:
        response = chat_completion(
            model=QUESTION_MODEL,
            messages=[
                {"role": "system", "content": "You identify critical information gaps in RFP requirements. Be very selective - only truly critical gaps. Keep questions concise."},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=800,
        )
        
        # Parse response
        cleaned = response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        
        result = json.loads(cleaned)
        
        if not result.get("has_critical_gap", False) or not result.get("question"):
            logger.info("No more critical questions needed")
            return None, 0
        
        question = result["question"]
        question["priority"] = "high"
        remaining = result.get("remaining_gaps", 0)
        
        logger.info(
            "Next critical question for %s: %s (remaining_gaps=%d)",
            question.get("requirement_id", "unknown"),
            question.get("question_text", "")[:60],
            remaining,
        )
        
        return question, remaining
        
    except json.JSONDecodeError as e:
        logger.error("Failed to parse critical question response: %s", e)
        return None, 0
    except Exception as e:
        logger.error("Critical question generation failed: %s", e)
        return None, 0


def check_if_more_questions_needed(
    requirements_result: RequirementsResult,
    company_kb: CompanyKnowledgeBase,
    rag_system: Optional[RAGSystem],
    all_answers: List[Answer],
) -> Tuple[bool, Optional[Dict[str, Any]], int]:
    """
    After an answer is received, check if more questions are needed.
    
    Returns:
        - needs_more: bool
        - next_question: dict or None
        - remaining_gaps: int
    """
    question, remaining = get_next_critical_question(
        requirements_result=requirements_result,
        company_kb=company_kb,
        rag_system=rag_system,
        previous_answers=all_answers,
    )
    
    if question is None:
        return False, None, 0
    
    return True, question, remaining


# =============================================================================
# ORIGINAL FUNCTIONS
# =============================================================================


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
    max_questions_per_requirement: int = 1,  # Reduced: only 1 critical question per requirement max
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

        user_prompt = f"""Analyze this RFP requirement and identify ONLY the CRITICAL information gaps that would make it IMPOSSIBLE to write a credible response without vendor input.

REQUIREMENT TO ANALYZE:
ID: {req.id}
Type: {req.type}
Category: {req.category}
Requirement Text: {req.source_text}

KNOWN COMPANY INFORMATION (already available - DO NOT ask about):
{known_info_text}

RAG CONTEXT (PRIOR RFP ANSWERS - already available - DO NOT ask about):
{rag_context or "[No RAG context available]"}

STRICT RULES - READ CAREFULLY:

1. **BE EXTREMELY SELECTIVE** - Only ask questions where:
   - The answer CANNOT be found in the knowledge base or RAG context above
   - Without this info, the response would be FACTUALLY WRONG or IMPOSSIBLE to write
   - A reasonable LLM response CANNOT be generated without this specific vendor input

2. **DO NOT ASK about:**
   - Generic capabilities (assume standard enterprise-grade solution)
   - Technical details that can be inferred from standard practice
   - Information that appears in the RAG context above
   - Nice-to-have details that would only slightly improve the response
   - Anything where a reasonable default answer could work

3. **ONLY ASK about:**
   - Specific numbers the RFP explicitly requests (team sizes, timelines, pricing)
   - Vendor-specific case studies or references if explicitly required
   - Unique commitments only the vendor can make
   - Information that if wrong would be embarrassing or disqualifying

4. **If in doubt, DON'T ASK** - It's better to generate a reasonable response than to ask too many questions.

Output a JSON array. For each CRITICAL gap (expect 0-1 per requirement), include:
- question_text: Clear, specific question
- context: Why this is CRITICAL (not just helpful)
- category: Type (resources, timeline, commercial, etc.)
- priority: ONLY use "high" - if it's not high priority, don't include it

Return an EMPTY ARRAY [] if:
- The requirement can be answered with knowledge base + RAG info
- The requirement is straightforward and doesn't require specific vendor commitments
- You're unsure if a question is truly critical
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
    
    # CRITICAL: Only keep HIGH priority questions - skip medium/low
    # This drastically reduces question count to only truly essential ones
    critical_questions = [q for q in filtered_questions if q.get("priority") == "high"]
    
    logger.info(
        "Generated %d CRITICAL questions from %d requirements (filtered %d total, %d high priority)",
        len(critical_questions),
        len(requirements_result.solution_requirements),
        len(all_questions),
        len(critical_questions),
    )
    
    # If we have too many critical questions, consolidate to most important ones
    if len(critical_questions) > 5:
        critical_questions = _consolidate_critical_questions(critical_questions, company_kb)
    
    return critical_questions, rag_contexts_by_req


def _consolidate_critical_questions(
    questions: List[Dict[str, Any]],
    company_kb: CompanyKnowledgeBase,
    max_questions: int = 5,
) -> List[Dict[str, Any]]:
    """
    Use LLM to consolidate/dedupe questions and keep only the most critical ones.
    This reduces question overload when many high-priority questions are generated.
    """
    if len(questions) <= max_questions:
        return questions
    
    logger.info("Consolidating %d critical questions down to max %d", len(questions), max_questions)
    
    questions_text = "\n".join([
        f"{i+1}. [{q.get('requirement_id', 'unknown')}] {q['question_text']}"
        for i, q in enumerate(questions)
    ])
    
    user_prompt = f"""You have {len(questions)} questions to ask a vendor about their RFP response. This is too many.

QUESTIONS:
{questions_text}

TASK:
Select the {max_questions} MOST CRITICAL questions that:
1. Cannot be answered without vendor input (truly need their specific info)
2. Would make the biggest difference to response quality
3. Are not redundant with each other

Some questions may be asking similar things - pick only one.
Some questions may be nice-to-have rather than critical - skip those.

Output a JSON array of the question numbers (1-indexed) to KEEP, e.g. [1, 3, 5, 8, 12]
Only output the JSON array, nothing else.
"""

    try:
        response = chat_completion(
            model=QUESTION_MODEL,
            messages=[
                {"role": "system", "content": "You select the most critical questions from a list. Be very selective."},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=200,
        )
        
        cleaned = response.replace("```json", "").replace("```", "").strip()
        selected_indices = json.loads(cleaned)
        
        if isinstance(selected_indices, list):
            # Convert 1-indexed to 0-indexed and filter
            result = []
            for idx in selected_indices[:max_questions]:
                if isinstance(idx, int) and 1 <= idx <= len(questions):
                    result.append(questions[idx - 1])
            
            logger.info("Consolidated to %d critical questions", len(result))
            return result if result else questions[:max_questions]
        
    except Exception as e:
        logger.warning("Failed to consolidate questions: %s, returning first %d", e, max_questions)
    
    return questions[:max_questions]


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

