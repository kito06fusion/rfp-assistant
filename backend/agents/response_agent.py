from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional

from backend.llm.client import chat_completion
from backend.models import BuildQuery, ResponseResult
from backend.rag import RAGSystem
from backend.knowledge_base import FusionAIxKnowledgeBase

logger = logging.getLogger(__name__)

RESPONSE_MODEL = "gpt-5-chat"

RESPONSE_SYSTEM_PROMPT = """You are an RFP response writer for fusionAIx. Write comprehensive, detailed responses to specific requirements.

CRITICAL RULES:
- Address ONLY the specific requirement provided - no executive summaries, no solution overviews, no generic introductions
- Show understanding of the requirement first, then provide a comprehensive, detailed response
- Be specific and concrete - use fusionAIx capabilities, case studies, and accelerators where relevant
- **CRITICAL: If USER-PROVIDED INFORMATION (Q&A) is provided, you MUST use the FULL, COMPLETE answers - do NOT summarize or condense them. If the user provided detailed project information, include those full details. If they provided certifications, include the full list. Match the depth and detail level of the Q&A answers.**
- **NEVER make up information (numbers, metrics, team sizes, etc.) - if the requirement asks for specific information and it's not in the Q&A or knowledge base, you should note that this information needs to be provided.**
- Write 800-1500 words (5000-10000 characters) - be comprehensive and detailed, matching the depth of the questions asked
- Use RAG examples for CONTENT only (facts, capabilities), NOT for structure
- NO sections like "Executive Summary", "Proposed Solution Overview", "Introduction" - just answer the requirement directly
- Document formatting handled automatically - provide clean text content only
- When Q&A context is provided, integrate the FULL information naturally throughout your response - don't just list it, weave it into a cohesive answer with all the details"""


def format_retrieved_chunks(chunks: List[Dict[str, Any]]) -> str:
    if not chunks:
        return ""

    formatted = ["RAG Examples (content only, ignore layout):"]
    for i, chunk in enumerate(chunks, 1):
        chunk_text = chunk.get('chunk_text', '')
        if len(chunk_text) > 800:
            chunk_text = chunk_text[:800] + "..."
        
        formatted.append(f"[Ex{i}] {chunk_text}")

    return "\n".join(formatted)


def run_response_agent(
    build_query: BuildQuery,
    rag_system: Optional[RAGSystem] = None,
    num_retrieval_chunks: int = 5,
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
    knowledge_base: Optional[FusionAIxKnowledgeBase] = None,
    qa_context: Optional[str] = None,
) -> ResponseResult:
    if not build_query.confirmed:
        raise ValueError("Build query must be confirmed before generating response")

    logger.info(
        "Response agent: starting (query_length=%d, has_rag=%s, num_chunks=%d)",
        len(build_query.query_text),
        rag_system is not None,
        num_retrieval_chunks,
    )

    retrieved_chunks: List[Dict[str, Any]] = []
    if rag_system is not None:
        try:
            req_summary = build_query.solution_requirements_summary[:400]
            struct_summary = build_query.response_structure_requirements_summary[:400]
            search_query = f"{req_summary}\n{struct_summary}"
            actual_chunks = min(num_retrieval_chunks, 4)
            retrieved_chunks = rag_system.search(search_query, k=actual_chunks)
            logger.info("Retrieved %d chunks from RAG (limited to %d)", len(retrieved_chunks), actual_chunks)
        except Exception as e:
            logger.warning("Failed to retrieve chunks from RAG: %s", str(e))
            retrieved_chunks = []

    chunks_text = format_retrieved_chunks(retrieved_chunks)
    
    fusionaix_context = ""
    if knowledge_base is not None:
        try:
            requirement_text = build_query.solution_requirements_summary[:300]  # Limit input
            fusionaix_context = knowledge_base.format_for_prompt(requirement_text)
            if len(fusionaix_context) > 600:
                fusionaix_context = fusionaix_context[:600] + "..."
            logger.info("Included fusionAIx knowledge base context in prompt (%d chars)", len(fusionaix_context))
        except Exception as kb_exc:
            logger.warning("Failed to format knowledge base context: %s", kb_exc)
            fusionaix_context = ""

    # Use FULL requirements - do not truncate, as we need all details
    req_summary = build_query.solution_requirements_summary
    struct_summary = build_query.response_structure_requirements_summary
    
    user_prompt_parts = [
        f"REQUIREMENT TO ADDRESS:",
        req_summary,
        "",
    ]
    
    if struct_summary and struct_summary != "No response structure requirements found.":
        user_prompt_parts.extend([
            "NOTE: Response structure requirements (formatting/style guidance only):",
            struct_summary,
            "These are for overall document formatting - do NOT add sections like 'Executive Summary' to individual requirement responses.",
            "",
        ])
    
    if fusionaix_context:
        user_prompt_parts.append(f"FUSIONAIX CONTEXT: {fusionaix_context}")
        user_prompt_parts.append("")
    
    if chunks_text:
        user_prompt_parts.append(f"PRIOR RFP EXAMPLES (for content/info only): {chunks_text}")
        user_prompt_parts.append("")
    
    if qa_context:
        user_prompt_parts.extend([
            "=" * 80,
            "USER-PROVIDED INFORMATION (CRITICAL - MUST USE FULL DETAILS):",
            "=" * 80,
            qa_context,
            "",
            "CRITICAL INSTRUCTIONS FOR USING Q&A INFORMATION:",
            "- The Q&A above contains SPECIFIC, DETAILED information that the user provided about their solution.",
            "- You MUST use the FULL, COMPLETE answers from the Q&A - do NOT summarize or condense them.",
            "- If a question asks about previous projects, use the FULL project details provided in the answer.",
            "- If a question asks about certifications, use the FULL list of certifications provided.",
            "- If a question asks about team structure, use the FULL team details provided.",
            "- If a question asks about capabilities, use the FULL capability descriptions provided.",
            "- Integrate the COMPLETE information naturally throughout your response - do NOT reduce it to one sentence.",
            "- The user provided detailed answers for a reason - they want those details in the response.",
            "- Match the depth and detail level of the Q&A answers in your response.",
            "",
        ])
    
    user_prompt_parts.extend([
        "TASK: Write a comprehensive, detailed response to the requirement above.",
        "",
        "YOUR RESPONSE SHOULD:",
        "1. Show understanding: Briefly acknowledge what the requirement asks for",
        "2. Comprehensive answer: Provide a detailed, thorough response addressing ALL aspects of the requirement",
        "3. Use Q&A information FULLY: If Q&A context is provided above, use the COMPLETE, FULL answers - do not summarize them. If the user provided detailed project information, include those full details. If they provided a list of certifications, include the full list. Match the depth of detail provided in the Q&A.",
        "4. Be specific: Include concrete details, metrics, capabilities, and examples",
        "5. Be relevant: Use fusionAIx capabilities, case studies, or accelerators where applicable",
        "6. Be detailed: Write 800-1500 words (5000-10000 characters) - match the depth of the questions asked",
        "",
        "DO NOT INCLUDE:",
        "- Executive summaries",
        "- Solution overviews",
        "- Generic introductions or conclusions",
        "- Unnecessary section headers - just answer the requirement directly",
        "- Any structure copied from prior RFP examples",
        "",
        "Write your comprehensive response now (detailed, 5000-10000 characters):",
    ])

    user_prompt = "\n".join(user_prompt_parts)
    
    system_tokens = len(RESPONSE_SYSTEM_PROMPT) // 4
    user_tokens = len(user_prompt) // 4
    total_input_tokens = system_tokens + user_tokens + 100  # +100 for overhead
    logger.info(
        "Prompt tokens: system=%d, user=%d, total_input=%d",
        system_tokens,
        user_tokens,
        total_input_tokens,
    )

    if max_tokens is None:
        estimated_input_tokens = total_input_tokens
        # Increased max_tokens to allow for detailed responses (800-1500 words = 5000-10000 chars)
        max_tokens = min(2500, 32769 - estimated_input_tokens - 1000)
        logger.info(
            "Response max_tokens set to %d (target: ~5000-10000 characters, ~800-1500 words)",
            max_tokens,
        )

    logger.info(
        "Response agent: calling LLM (model=%s, temperature=%s, max_tokens=%s)",
        RESPONSE_MODEL,
        temperature,
        max_tokens,
    )

    response_text = chat_completion(
        model=RESPONSE_MODEL,
        messages=[
            {"role": "system", "content": RESPONSE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    
    MAX_RESPONSE_LENGTH = 10000  # Increased to allow detailed responses
    if len(response_text) > MAX_RESPONSE_LENGTH:
        logger.warning(
            "Response too long (%d chars), truncating to %d chars",
            len(response_text),
            MAX_RESPONSE_LENGTH,
        )
        truncated = response_text[:MAX_RESPONSE_LENGTH]
        last_period = truncated.rfind('.')
        last_newline = truncated.rfind('\n')
        cut_point = max(last_period, last_newline)
        if cut_point > MAX_RESPONSE_LENGTH * 0.8:  # Only if we find a good break point
            response_text = truncated[:cut_point + 1] + "\n\n[Response truncated for length]"
        else:
            response_text = truncated + "\n\n[Response truncated for length]"

    logger.info(
        "Response agent: finished (response_length=%d, chunks_used=%d, max_allowed=%d)",
        len(response_text),
        len(retrieved_chunks),
        MAX_RESPONSE_LENGTH,
    )

    return ResponseResult(
        response_text=response_text,
        build_query_used=build_query.query_text,
        num_retrieved_chunks=len(retrieved_chunks),
        notes=f"Generated with {len(retrieved_chunks)} RAG chunks" if retrieved_chunks else "Generated without RAG",
    )

