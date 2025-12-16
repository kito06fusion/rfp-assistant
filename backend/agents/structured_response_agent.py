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
from backend.agents.prompts import STRUCTURED_RESPONSE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
STRUCTURED_RESPONSE_MODEL = "gpt-5-chat"


def format_retrieved_chunks(
    chunks: List[Dict[str, Any]],
    max_chunks: int = 4,
    max_total_chars: int = 3000,
) -> str:
    """
    Format RAG chunks for inclusion in the structured-response prompt while:
    - de-duplicating similar evidence chunks
    - enforcing a total character budget to keep token usage reasonable
    """
    if not chunks:
        return ""

    formatted: List[str] = ["RAG Examples (for content reference only):"]
    seen_normalized: set[str] = set()
    total_chars = 0
    example_idx = 1

    for chunk in chunks:
        if example_idx > max_chunks or total_chars >= max_total_chars:
            break

        chunk_text = chunk.get("chunk_text", "") or ""
        norm = " ".join(chunk_text.split()).lower()
        if not norm or norm in seen_normalized:
            continue
        seen_normalized.add(norm)

        if len(chunk_text) > 800:
            chunk_text = chunk_text[:800] + "..."

        if total_chars + len(chunk_text) > max_total_chars:
            remaining = max_total_chars - total_chars
            if remaining <= 0:
                break
            chunk_text = chunk_text[:remaining] + "..."

        formatted.append(f"[Ex{example_idx}] {chunk_text}")
        total_chars += len(chunk_text)
        example_idx += 1

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
    if not structure_detection.has_explicit_structure:
        raise ValueError("Cannot generate structured response without explicit structure")
    
    logger.info(
        "Structured response agent: starting (sections=%d, solution_reqs=%d)",
        len(structure_detection.detected_sections),
        len(requirements_result.solution_requirements),
    )
    
    retrieved_chunks: List[Dict[str, Any]] = []
    if rag_system is not None:
        try:
            all_chunks = []
            seen_chunk_ids = set()
            
            structure_chunks = rag_system.search(structure_detection.structure_description, k=min(3, num_retrieval_chunks))
            for chunk in structure_chunks:
                chunk_id = chunk.get("chunk_id") or str(chunk.get("chunk_text", ""))[:50]
                if chunk_id not in seen_chunk_ids:
                    all_chunks.append(chunk)
                    seen_chunk_ids.add(chunk_id)
            
            for req in requirements_result.solution_requirements[:5]:  # Search top 5 requirements
                if len(all_chunks) >= num_retrieval_chunks * 2:  # Limit total chunks
                    break
                try:
                    req_chunks = rag_system.search(req.normalized_text, k=min(2, num_retrieval_chunks))
                    for chunk in req_chunks:
                        chunk_id = chunk.get("chunk_id") or str(chunk.get("chunk_text", ""))[:50]
                        if chunk_id not in seen_chunk_ids:
                            all_chunks.append(chunk)
                            seen_chunk_ids.add(chunk_id)
                except Exception as req_e:
                    logger.warning("Failed to search RAG for requirement %s: %s", req.id, req_e)
            
            retrieved_chunks = all_chunks[:num_retrieval_chunks * 2]  # Allow more chunks for structured response
            logger.info("Retrieved %d chunks from RAG (searched structure + %d requirements)", len(retrieved_chunks), min(5, len(requirements_result.solution_requirements)))
        except Exception as e:
            logger.warning("Failed to retrieve chunks from RAG: %s", str(e))
            retrieved_chunks = []
    
    chunks_text = format_retrieved_chunks(retrieved_chunks, max_chunks=8, max_total_chars=5000)
    
    fusionaix_context = ""
    if knowledge_base is not None:
        try:
            req_text = " ".join([
                req.normalized_text[:200]  # Increased from 100 to 200 chars per requirement
                for req in requirements_result.solution_requirements[:8]  # Increased from 3 to 8 requirements
            ])
            fusionaix_context = knowledge_base.format_for_prompt(req_text)
            # Increased limit from 1000 to 3000 chars for more comprehensive context
            if len(fusionaix_context) > 3000:
                fusionaix_context = fusionaix_context[:3000] + "..."
            logger.info("Included fusionAIx knowledge base context (%d chars, from %d requirements)", len(fusionaix_context), min(8, len(requirements_result.solution_requirements)))
        except Exception as kb_exc:
            logger.warning("Failed to format knowledge base context: %s", kb_exc)
            fusionaix_context = ""
    
    solution_reqs_text = "\n".join([
        f"- [{req.type.upper()}] {req.normalized_text}"
        for req in requirements_result.solution_requirements
    ])
    
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
        "3. Be comprehensive and detailed - write 1500-3000 words per major section. Each section should be thorough, specific, and address multiple requirements where relevant",
        "4. Use Q&A information FULLY: If Q&A context is provided above, use the COMPLETE, FULL answers - do not summarize them. If the user provided detailed project information, include those full details. If they provided a list of certifications, include the full list. Match the depth of detail provided in the Q&A.",
        "5. Use fusionAIx capabilities, case studies, and accelerators where relevant",
        "6. Follow the structure EXACTLY as specified",
        "7. Include specific details, metrics, and concrete examples throughout",
        "8. Be as detailed as the per-requirement responses would be - this is a complete document, not a summary",
        "9. Each section should be comprehensive enough to stand alone as a detailed response",
        "",
        "Generate the complete structured response now:",
    ])
    
    user_prompt = "\n".join(user_prompt_parts)
    
    system_tokens = len(STRUCTURED_RESPONSE_SYSTEM_PROMPT) // 4
    user_tokens = len(user_prompt) // 4
    total_input_tokens = system_tokens + user_tokens + 100
    
    if max_tokens is None:
        num_sections = len(structure_detection.detected_sections)
        num_requirements = len(requirements_result.solution_requirements)
        estimated_output_tokens = max(12000, num_sections * 2500 + num_requirements * 200)
        # Model supports max 16384 completion tokens, so cap at that
        max_tokens = min(estimated_output_tokens, 16384)
        logger.info("Calculated max_tokens: %d (sections=%d, requirements=%d, estimated_output=%d)", 
                   max_tokens, num_sections, num_requirements, estimated_output_tokens)
    
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

