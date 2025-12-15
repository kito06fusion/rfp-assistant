"""
Question Generation Agent

Analyzes build queries and identifies information gaps. Generates questions for unknown information
that is not available in the company knowledge base. The LLM analyzes the build query to determine
what information is needed to generate a proper response.
"""

from __future__ import annotations

import json
import logging
from typing import List, Dict, Any, Optional

from backend.llm.client import chat_completion
from backend.models import RequirementItem
from backend.knowledge_base.company_kb import CompanyKnowledgeBase

logger = logging.getLogger(__name__)
QUESTION_MODEL = "gpt-5-chat"

QUESTION_SYSTEM_PROMPT = """You are an expert at analyzing RFP requirements and identifying what information a VENDOR/RESPONDER needs to provide to create a complete, concrete response.

CRITICAL CONTEXT:
- You are helping a VENDOR/RESPONDER (the user) create a response to an RFP
- The RFP contains requirements that the BUYER has specified
- Your goal is to identify what information the VENDOR needs to provide about THEIR SOLUTION to answer each requirement
- You are NOT asking the vendor to clarify what the RFP requires - the RFP is already clear
- You ARE asking the vendor what THEY can offer/provide/commit to in their response
- **CRITICAL: If a requirement EXPECTS or ASKS FOR specific information (team structure, resourcing numbers, certifications, previous projects, timelines, implementation details, etc.), you MUST ask the vendor about that information. The LLM cannot make up this information - it must come from the vendor.**

EXAMPLE OF WRONG APPROACH:
❌ "What specific SLA metrics does the RFP require?" (asking vendor to clarify RFP)
❌ "How many internal and external users does the RFP specify?" (asking vendor to clarify RFP)

EXAMPLE OF CORRECT APPROACH:
✅ "What SLA metrics and performance targets does your solution support for monitoring?" (asking vendor about their solution)
✅ "What is your typical response time SLA that you can commit to?" (asking vendor about their capabilities)
✅ "How many concurrent users can your platform support?" (asking vendor about their solution capacity)

IMPORTANT RULES:
1. DO NOT ask about information that is already in the company knowledge base (platforms, technologies, certifications, pricing models, etc.)
2. DO ask about:
   - What the vendor's solution can provide/offer (e.g., "What SLA metrics does your solution support?")
   - What the vendor can commit to (e.g., "What response time SLA can you commit to?")
   - Vendor-specific capabilities (e.g., "How many concurrent users can your platform support?")
   - Vendor's typical approach or methodology (e.g., "What is your typical implementation timeline for similar projects?")
   - Vendor's experience or case studies (e.g., "Do you have case studies for similar government projects?")
   - Vendor's team structure or resources (e.g., "What team structure do you propose for this project?")
   - Vendor's pricing or commercial terms (e.g., "What is your pricing model for this type of project?")
3. **CRITICAL: If the requirement explicitly ASKS FOR or EXPECTS specific information (e.g., "provide team structure", "include resourcing numbers", "list certifications", "describe previous projects", "specify timelines"), you MUST ask the vendor about that information. The LLM cannot make up this information - it must come from the vendor.**
4. NEVER ask questions that seek to clarify what the RFP requires - the RFP is the source of truth
5. ALWAYS frame questions as asking the vendor about THEIR solution, capabilities, or offerings
6. Generate CLEAR, SPECIFIC questions that help the vendor describe their solution
7. Each question should help the vendor provide concrete information about their response to the requirement
8. Focus on information that is CRITICAL to creating a complete response about the vendor's solution
9. **If a requirement mentions specific information that should be provided (numbers, metrics, team details, certifications, project examples), ask about it - do not assume the LLM can generate this information.**

For each question, provide:
- question_text: The question to ask the vendor about their solution (be specific and clear)
- context: Why this information is needed to create a complete response to requirement X (explain how it helps answer the requirement)
- category: Type of question (technical, business, implementation, commercial, timeline, resources, etc.)
- priority: "high" (critical for answering the requirement), "medium", or "low"

Output JSON with a list of questions."""


def generate_questions(
    requirement: RequirementItem,
    all_requirements: List[RequirementItem],
    company_kb: CompanyKnowledgeBase,
) -> List[Dict[str, Any]]:
    """
    Generate questions for unknown information in a requirement.
    
    Args:
        requirement: The requirement to analyze
        all_requirements: All requirements for context
        company_kb: Company knowledge base to check against
        
    Returns:
        List of question dictionaries with question_text, context, category, priority
    """
    logger.info(
        "Question agent: analyzing requirement %s for information gaps",
        requirement.id,
    )
    
    # Check what we know
    known_topics = company_kb.get_all_known_topics()
    known_info_text = company_kb.format_for_prompt()
    
    # Build context from all requirements
    all_req_text = "\n\n".join([
        f"[{req.id}] {req.normalized_text}"
        for req in all_requirements[:10]  # Limit to first 10 for context
    ])
    
    user_prompt = f"""Analyze the following requirement and identify what information is MISSING or UNCLEAR that would be needed to create a proper response.

KNOWN COMPANY INFORMATION (DO NOT ask about these):
{known_info_text}

REQUIREMENT TO ANALYZE:
[{requirement.id}] {requirement.normalized_text}

Source Text: {requirement.source_text}

CONTEXT FROM OTHER REQUIREMENTS:
{all_req_text}

TASK:
1. Identify information gaps in the requirement
2. Check if information is in the known company info (if yes, don't ask)
3. Generate specific, clear questions for missing information
4. Prioritize questions by importance

Output JSON array of questions, each with:
- question_text: string (the question)
- context: string (why this is important)
- category: string (technical, business, implementation, timeline, etc.)
- priority: string ("high", "medium", or "low")

If no questions are needed (all information is clear or in knowledge base), return empty array [].
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
        
        # Parse JSON response
        cleaned = content.replace("```json", "").replace("```", "").strip()
        try:
            questions = json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to extract JSON array
            import re
            array_match = re.search(r'\[.*\]', cleaned, re.DOTALL)
            if array_match:
                questions = json.loads(array_match.group(0))
            else:
                logger.warning("Could not parse questions JSON, returning empty list")
                questions = []
        
        # Validate questions
        if not isinstance(questions, list):
            questions = []
        
        validated_questions = []
        for q in questions:
            if isinstance(q, dict) and "question_text" in q:
                # Ensure all required fields
                validated_q = {
                    "question_text": q.get("question_text", ""),
                    "context": q.get("context", ""),
                    "category": q.get("category", "general"),
                    "priority": q.get("priority", "medium"),
                }
                if validated_q["question_text"]:
                    validated_questions.append(validated_q)
        
        # Filter out questions about known topics
        filtered_questions = []
        for q in validated_questions:
            question_text = q["question_text"].lower()
            # Check if question is about something we know
            should_skip = False
            for topic in known_topics:
                if topic.lower() in question_text:
                    # Double-check with KB
                    if company_kb.has_info(topic):
                        logger.debug("Skipping question about known topic: %s", topic)
                        should_skip = True
                        break
            if not should_skip:
                filtered_questions.append(q)
        
        logger.info(
            "Question agent: generated %d questions (filtered from %d)",
            len(filtered_questions),
            len(validated_questions),
        )
        
        return filtered_questions
        
    except Exception as e:
        logger.error("Question generation failed: %s", e)
        logger.exception("Full traceback:")
        return []


def analyze_build_query_for_questions(
    build_query: BuildQuery,
    requirements_result: RequirementsResult,
    company_kb: CompanyKnowledgeBase,
    max_questions_per_requirement: int = 3,
) -> List[Dict[str, Any]]:
    """
    Analyze each requirement individually and generate questions about missing information.
    
    Args:
        build_query: The build query containing all requirements
        requirements_result: The requirements result with individual requirements
        company_kb: Company knowledge base
        max_questions_per_requirement: Maximum questions per requirement
        
    Returns:
        List of questions (as dictionaries) with requirement_id
    """
    logger.info("Analyzing requirements individually for information gaps")
    
    # Get company knowledge summary
    known_info_text = company_kb.format_for_prompt()
    
    all_questions = []
    
    # Analyze each solution requirement individually
    for req in requirements_result.solution_requirements:
        logger.info("Analyzing requirement %s for information gaps", req.id)
        
        # Build context from other requirements
        other_reqs_text = "\n".join([
            f"[{r.id}] {r.normalized_text}"
            for r in requirements_result.solution_requirements
            if r.id != req.id
        ])
        
        user_prompt = f"""Analyze this RFP requirement and identify what information the VENDOR needs to provide about THEIR SOLUTION to create a complete response.

REQUIREMENT TO ANALYZE:
ID: {req.id}
Type: {req.type}
Category: {req.category}
Requirement Text: {req.normalized_text}
Original Source: {req.source_text}

CONTEXT - OTHER REQUIREMENTS (for reference):
{other_reqs_text[:1000] if len(other_reqs_text) > 1000 else other_reqs_text}

RESPONSE STRUCTURE REQUIREMENTS (how to format the response):
{build_query.response_structure_requirements_summary[:500]}

KNOWN COMPANY INFORMATION (DO NOT ask about these):
{known_info_text}

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
            
            # Parse JSON response
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
            
            # Validate and add requirement_id to each question
            for q in questions:
                if isinstance(q, dict) and "question_text" in q:
                    validated_q = {
                        "question_text": q.get("question_text", ""),
                        "context": q.get("context", ""),
                        "category": q.get("category", "general"),
                        "priority": q.get("priority", "medium"),
                        "requirement_id": req.id,  # Link question to requirement
                    }
                    if validated_q["question_text"]:
                        all_questions.append(validated_q)
            
            # Limit questions per requirement
            req_questions = [q for q in all_questions if q.get("requirement_id") == req.id]
            if len(req_questions) > max_questions_per_requirement:
                # Keep only the highest priority questions for this requirement
                priority_order = {"high": 0, "medium": 1, "low": 2}
                req_questions.sort(key=lambda q: priority_order.get(q.get("priority", "medium"), 1))
                # Remove excess questions
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
    
    # Filter out questions about known topics
    filtered_questions = []
    known_topics = company_kb.get_all_known_topics()
    for q in all_questions:
        question_text = q["question_text"].lower()
        # Check if question is about something we know
        should_skip = False
        for topic in known_topics:
            if topic.lower() in question_text:
                # Double-check with KB
                if company_kb.has_info(topic):
                    logger.debug("Skipping question about known topic: %s", topic)
                    should_skip = True
                    break
        if not should_skip:
            filtered_questions.append(q)
    
    # Sort by priority and requirement order
    priority_order = {"high": 0, "medium": 1, "low": 2}
    filtered_questions.sort(key=lambda q: (
        priority_order.get(q.get("priority", "medium"), 1),
        q.get("requirement_id", ""),  # Group by requirement
    ))
    
    logger.info(
        "Generated %d total questions from %d requirements (filtered from %d)",
        len(filtered_questions),
        len(requirements_result.solution_requirements),
        len(all_questions),
    )
    
    return filtered_questions


def analyze_build_query_for_questions_legacy(
    build_query: BuildQuery,
    company_kb: CompanyKnowledgeBase,
    max_questions: int = 20,
) -> List[Dict[str, Any]]:
    """
    Legacy function: Analyze build query as a whole (used when requirements are not available).
    Prefer analyze_build_query_for_questions with requirements_result for better per-requirement analysis.
    """
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
        
        # Filter out questions about known topics
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
        logger.error("Question generation failed: %s", e)
        return []
        
    except Exception as e:
        logger.error("Question generation from build query failed: %s", e)
        logger.exception("Full traceback:")
        return []


def analyze_requirements_for_questions(
    requirements: List[RequirementItem],
    company_kb: CompanyKnowledgeBase,
    max_questions_per_requirement: int = 3,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Analyze multiple requirements and generate questions for each.
    
    Args:
        requirements: List of requirements to analyze
        company_kb: Company knowledge base
        max_questions_per_requirement: Maximum questions per requirement
        
    Returns:
        Dictionary mapping requirement_id to list of questions
    """
    all_questions = {}
    
    for req in requirements:
        questions = generate_questions(req, requirements, company_kb)
        # Limit questions per requirement
        questions = questions[:max_questions_per_requirement]
        # Sort by priority (high first)
        priority_order = {"high": 0, "medium": 1, "low": 2}
        questions.sort(key=lambda q: priority_order.get(q.get("priority", "medium"), 1))
        all_questions[req.id] = questions
    
    total_questions = sum(len(qs) for qs in all_questions.values())
    logger.info(
        "Analyzed %d requirements, generated %d total questions",
        len(requirements),
        total_questions,
    )
    
    return all_questions

