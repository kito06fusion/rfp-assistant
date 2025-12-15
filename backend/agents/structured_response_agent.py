from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.llm.client import chat_completion
from backend.models import (
    ExtractionResult,
    RequirementsResult,
    StructureDetectionResult,
    ResponseResult,
)
from backend.rag import RAGSystem
from backend.knowledge_base import FusionAIxKnowledgeBase

logger = logging.getLogger(__name__)
STRUCTURED_RESPONSE_MODEL = "gpt-5-chat"

STRUCTURED_RESPONSE_SYSTEM_PROMPT = """You are an RFP response writer for fusionAIx. Generate a complete RFP response document following the EXACT structure specified in the RFP.

CRITICAL RULES:
- Follow the RFP's required structure EXACTLY - include all specified sections in the required order
- Each section should address relevant solution requirements from the RFP
- Be specific and concrete - use fusionAIx capabilities, case studies, and accelerators where relevant
- **CRITICAL: If USER-PROVIDED INFORMATION (Q&A) is provided, you MUST use the FULL, COMPLETE answers - do NOT summarize or condense them. If the user provided detailed project information, include those full details. If they provided certifications, include the full list. Match the depth and detail level of the Q&A answers.**
- **NEVER make up information (numbers, metrics, team sizes, etc.) - if the requirement asks for specific information and it's not in the Q&A or knowledge base, you should note that this information needs to be provided.**
- Maintain professional tone and clear organization
- Ensure all mandatory sections are included
- Map solution requirements to appropriate sections
- Provide comprehensive responses that fully address the RFP requirements
- When Q&A context is provided, integrate the FULL information naturally throughout relevant sections - don't just list it, weave it into a cohesive answer with all the details"""


def format_retrieved_chunks(chunks: List[Dict[str, Any]]) -> str:
    """Format RAG chunks for inclusion in prompt."""
    if not chunks:
        return ""
    
    formatted = ["RAG Examples (for content reference only):"]
    for i, chunk in enumerate(chunks, 1):
        chunk_text = chunk.get('chunk_text', '')
        if len(chunk_text) > 800:
            chunk_text = chunk_text[:800] + "..."
        formatted.append(f"[Ex{i}] {chunk_text}")
    
    return "\n".join(formatted)


def run_structured_response_agent(
    extraction_result: ExtractionResult,
    requirements_result: RequirementsResult,
    structure_detection: StructureDetectionResult,
    rag_system: Optional[RAGSystem] = None,
    num_retrieval_chunks: int = 5,
    knowledge_base: Optional[FusionAIxKnowledgeBase] = None,
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
    qa_context: Optional[str] = None,
) -> ResponseResult:
    """
    Generate RFP response following the explicit structure detected in the RFP.
    
    Args:
        extraction_result: Extraction result with RFP metadata
        requirements_result: Requirements result with solution and structure requirements
        structure_detection: Structure detection result with detected sections
        rag_system: Optional RAG system for prior RFP examples
        num_retrieval_chunks: Number of RAG chunks to retrieve
        knowledge_base: Optional fusionAIx knowledge base
        temperature: LLM temperature
        max_tokens: Maximum tokens for response
        
    Returns:
        ResponseResult with complete structured response
    """
    if not structure_detection.has_explicit_structure:
        raise ValueError("Cannot generate structured response without explicit structure")
    
    logger.info(
        "Structured response agent: starting (sections=%d, solution_reqs=%d)",
        len(structure_detection.detected_sections),
        len(requirements_result.solution_requirements),
    )
    
    # Retrieve RAG chunks if available
    retrieved_chunks: List[Dict[str, Any]] = []
    if rag_system is not None:
        try:
            # Use structure description and solution requirements for search
            search_query = f"{structure_detection.structure_description}\n{requirements_result.solution_requirements[0].normalized_text if requirements_result.solution_requirements else ''}"
            retrieved_chunks = rag_system.search(search_query, k=min(num_retrieval_chunks, 5))
            logger.info("Retrieved %d chunks from RAG", len(retrieved_chunks))
        except Exception as e:
            logger.warning("Failed to retrieve chunks from RAG: %s", str(e))
            retrieved_chunks = []
    
    chunks_text = format_retrieved_chunks(retrieved_chunks)
    
    # Get fusionAIx knowledge base context
    fusionaix_context = ""
    if knowledge_base is not None:
        try:
            # Use first few solution requirements for context
            req_text = " ".join([
                req.normalized_text[:100] 
                for req in requirements_result.solution_requirements[:3]
            ])
            fusionaix_context = knowledge_base.format_for_prompt(req_text)
            if len(fusionaix_context) > 1000:
                fusionaix_context = fusionaix_context[:1000] + "..."
            logger.info("Included fusionAIx knowledge base context (%d chars)", len(fusionaix_context))
        except Exception as kb_exc:
            logger.warning("Failed to format knowledge base context: %s", kb_exc)
            fusionaix_context = ""
    
    # Build solution requirements summary
    solution_reqs_text = "\n".join([
        f"- [{req.type.upper()}] {req.normalized_text}"
        for req in requirements_result.solution_requirements
    ])
    
    # Build user prompt
    user_prompt_parts = [
        "RFP RESPONSE STRUCTURE REQUIREMENTS:",
        structure_detection.structure_description,
        "",
        f"REQUIRED SECTIONS (in order):",
    ]
    
    for i, section in enumerate(structure_detection.detected_sections, 1):
        user_prompt_parts.append(f"{i}. {section}")
    
    user_prompt_parts.extend([
        "",
        "SOLUTION REQUIREMENTS TO ADDRESS:",
        solution_reqs_text,
        "",
    ])
    
    if fusionaix_context:
        user_prompt_parts.extend([
            "FUSIONAIX CONTEXT:",
            fusionaix_context,
            "",
        ])
    
    if chunks_text:
        user_prompt_parts.extend([
            chunks_text,
            "",
        ])
    
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
        "TASK: Generate a complete RFP response document following the EXACT structure above.",
        "",
        "YOUR RESPONSE MUST:",
        "1. Include ALL required sections in the specified order",
        "2. Address relevant solution requirements in each section",
        "3. Be comprehensive and detailed - write 1000-2000 words per major section",
        "4. Use Q&A information FULLY: If Q&A context is provided above, use the COMPLETE, FULL answers - do not summarize them. If the user provided detailed project information, include those full details. If they provided a list of certifications, include the full list. Match the depth of detail provided in the Q&A.",
        "5. Use fusionAIx capabilities, case studies, and accelerators where relevant",
        "6. Follow the structure EXACTLY as specified",
        "7. Include specific details, metrics, and concrete examples throughout",
        "",
        "Generate the complete structured response now:",
    ])
    
    user_prompt = "\n".join(user_prompt_parts)
    
    # Calculate tokens
    system_tokens = len(STRUCTURED_RESPONSE_SYSTEM_PROMPT) // 4
    user_tokens = len(user_prompt) // 4
    total_input_tokens = system_tokens + user_tokens + 100
    
    if max_tokens is None:
        # Allow more tokens for structured responses (they're longer, especially with Q&A context)
        max_tokens = min(8000, 32769 - total_input_tokens - 1000)
    
    logger.info(
        "Structured response agent: calling LLM (model=%s, temperature=%s, max_tokens=%s, input_tokens=%d)",
        STRUCTURED_RESPONSE_MODEL,
        temperature,
        max_tokens,
        total_input_tokens,
    )
    
    response_text = chat_completion(
        model=STRUCTURED_RESPONSE_MODEL,
        messages=[
            {"role": "system", "content": STRUCTURED_RESPONSE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    
    logger.info(
        "Structured response agent: finished (response_length=%d, chunks_used=%d)",
        len(response_text),
        len(retrieved_chunks),
    )
    
    return ResponseResult(
        response_text=response_text,
        build_query_used=f"Structured response following: {', '.join(structure_detection.detected_sections)}",
        num_retrieved_chunks=len(retrieved_chunks),
        notes=f"Generated structured response with {len(structure_detection.detected_sections)} sections, using {len(retrieved_chunks)} RAG chunks",
    )

