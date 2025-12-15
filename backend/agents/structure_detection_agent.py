from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from backend.llm.client import chat_completion
from backend.models import RequirementItem

logger = logging.getLogger(__name__)
STRUCTURE_DETECTION_MODEL = "gpt-5-chat"

STRUCTURE_DETECTION_SYSTEM_PROMPT = """You are an expert at analyzing RFP response structure requirements.

Your task is to determine if the RFP specifies an EXPLICIT response structure that must be followed.

EXPLICIT STRUCTURE means:
- The RFP clearly specifies sections/chapters that must be included (e.g., "Response must include: Executive Summary, Technical Approach, Implementation Plan, Pricing")
- The RFP provides a template or format that must be followed
- The RFP lists specific document sections in a required order
- The RFP mandates a particular response format with named sections

NOT EXPLICIT STRUCTURE (implicit/formatting only):
- General formatting guidelines (font size, margins, page numbers)
- Style requirements (professional tone, language)
- Submission requirements (file format, delivery method)
- Document organization hints without mandatory sections
- Generic instructions like "be clear and organized"

Analyze the response_structure_requirements and determine:
1. has_explicit_structure: boolean - true if explicit structure is found
2. structure_type: "explicit" | "implicit" | "none"
3. detected_sections: List of section names if explicit structure found (e.g., ["Executive Summary", "Technical Approach", "Implementation Plan"])
4. structure_description: Description of the required structure
5. confidence: float 0.0-1.0 indicating confidence in the detection

Output JSON with these fields."""

def detect_structure(
    response_structure_requirements: List[RequirementItem],
) -> Dict[str, Any]:
    """
    Detect if RFP specifies an explicit response structure.
    
    Args:
        response_structure_requirements: List of response structure requirement items
        
    Returns:
        Dictionary with structure detection results:
        - has_explicit_structure: bool
        - structure_type: "explicit" | "implicit" | "none"
        - detected_sections: List[str] (if explicit)
        - structure_description: str
        - confidence: float
    """
    if not response_structure_requirements:
        logger.info("Structure detection: No response structure requirements found")
        return {
            "has_explicit_structure": False,
            "structure_type": "none",
            "detected_sections": [],
            "structure_description": "No response structure requirements found in RFP.",
            "confidence": 1.0,
        }
    
    # Combine all response structure requirements into a single text
    structure_text = "\n\n".join([
        f"[{req.type.upper()}] {req.normalized_text}\nSource: {req.source_text}"
        for req in response_structure_requirements
    ])
    
    user_prompt = f"""Analyze the following response structure requirements from an RFP:

{structure_text}

Determine if these requirements specify an EXPLICIT response structure with mandatory sections/chapters, or if they are just formatting/style guidelines.

Output JSON with:
- has_explicit_structure: boolean
- structure_type: "explicit" | "implicit" | "none"
- detected_sections: array of section names (if explicit, e.g., ["Executive Summary", "Technical Approach"])
- structure_description: string describing the structure
- confidence: float between 0.0 and 1.0
"""
    
    logger.info(
        "Structure detection: analyzing %d response structure requirements",
        len(response_structure_requirements),
    )
    
    try:
        content = chat_completion(
            model=STRUCTURE_DETECTION_MODEL,
            messages=[
                {"role": "system", "content": STRUCTURE_DETECTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=1000,
        )
        
        # Parse JSON response
        cleaned = content.replace("```json", "").replace("```", "").strip()
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
            else:
                raise ValueError("Could not parse JSON from structure detection response")
        
        # Validate and normalize result
        has_explicit = result.get("has_explicit_structure", False)
        structure_type = result.get("structure_type", "none")
        detected_sections = result.get("detected_sections", [])
        structure_description = result.get("structure_description", "")
        confidence = float(result.get("confidence", 0.5))
        
        # Ensure structure_type matches has_explicit_structure
        if has_explicit and structure_type != "explicit":
            structure_type = "explicit"
        elif not has_explicit and structure_type == "explicit":
            has_explicit = False
            structure_type = "implicit" if detected_sections else "none"
        
        logger.info(
            "Structure detection: result - explicit=%s, type=%s, sections=%d, confidence=%.2f",
            has_explicit,
            structure_type,
            len(detected_sections),
            confidence,
        )
        
        return {
            "has_explicit_structure": has_explicit,
            "structure_type": structure_type,
            "detected_sections": detected_sections if isinstance(detected_sections, list) else [],
            "structure_description": structure_description or "No explicit structure detected.",
            "confidence": max(0.0, min(1.0, confidence)),
        }
        
    except Exception as e:
        logger.error("Structure detection failed: %s", e)
        logger.exception("Full traceback:")
        # Return safe default
        return {
            "has_explicit_structure": False,
            "structure_type": "none",
            "detected_sections": [],
            "structure_description": f"Structure detection failed: {str(e)}",
            "confidence": 0.0,
        }

