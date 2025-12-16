from __future__ import annotations

import logging
from typing import Dict, Any, List

from backend.llm.client import chat_completion
from backend.models import RequirementItem
from backend.agents.prompts import QUALITY_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
QUALITY_MODEL = "gpt-5-chat"


def assess_response_quality(
    requirement: RequirementItem,
    response_text: str,
) -> Dict[str, Any]:
    """
    Assess the quality of a response for a requirement.
    
    Args:
        requirement: The requirement being addressed
        response_text: The generated response text
        
    Returns:
        Dictionary with quality assessment:
        - score: float (0-100)
        - completeness: str (complete/partial/incomplete)
        - relevance: str (high/medium/low)
        - issues: List[str]
        - suggestions: List[str]
    """
    logger.info("Quality assessment: evaluating response for requirement %s", requirement.id)
    
    user_prompt = f"""Evaluate the quality of this RFP response:

REQUIREMENT:
{requirement.normalized_text}

Source: {requirement.source_text}

RESPONSE:
{response_text}

Provide a quality assessment with:
- score: 0-100 (how well does it address the requirement?)
- completeness: "complete", "partial", or "incomplete"
- relevance: "high", "medium", or "low"
- issues: List of specific problems or gaps
- suggestions: List of improvement suggestions

Output JSON format."""
    
    try:
        content = chat_completion(
            model=QUALITY_MODEL,
            messages=[
                {"role": "system", "content": QUALITY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=800,
        )
        
        # Parse JSON response
        import json
        import re
        cleaned = content.replace("```json", "").replace("```", "").strip()
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group(0))
        else:
            result = json.loads(cleaned)
        
        # Validate and normalize
        score = float(result.get("score", 50))
        score = max(0, min(100, score))
        
        completeness = result.get("completeness", "partial")
        if completeness not in ["complete", "partial", "incomplete"]:
            completeness = "partial"
        
        relevance = result.get("relevance", "medium")
        if relevance not in ["high", "medium", "low"]:
            relevance = "medium"
        
        issues = result.get("issues", [])
        if not isinstance(issues, list):
            issues = []
        
        suggestions = result.get("suggestions", [])
        if not isinstance(suggestions, list):
            suggestions = []
        
        logger.info(
            "Quality assessment: score=%.1f, completeness=%s, relevance=%s, issues=%d",
            score,
            completeness,
            relevance,
            len(issues),
        )
        
        return {
            "score": score,
            "completeness": completeness,
            "relevance": relevance,
            "issues": issues,
            "suggestions": suggestions,
        }
        
    except Exception as e:
        logger.error("Quality assessment failed: %s", e)
        return {
            "score": 50.0,
            "completeness": "unknown",
            "relevance": "unknown",
            "issues": [f"Quality assessment failed: {str(e)}"],
            "suggestions": [],
        }

