"""
Markdown Generator for RFP Responses

Generates Markdown format documents.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from backend.models import RequirementsResult, ExtractionResult

logger = logging.getLogger(__name__)


def generate_rfp_markdown(
    individual_responses: List[Dict[str, Any]],
    requirements_result: RequirementsResult,
    extraction_result: ExtractionResult,
    rfp_title: Optional[str] = None,
    output_path: Optional[Path] = None,
) -> bytes:
    """
    Generate a Markdown document from RFP responses.
    
    Args:
        individual_responses: List of individual requirement responses
        requirements_result: RequirementsResult containing all requirements
        extraction_result: ExtractionResult with RFP metadata
        rfp_title: Optional title for the RFP
        output_path: Optional path to save Markdown (if None, returns bytes)
    
    Returns:
        Markdown bytes if output_path is None, otherwise writes to file
    """
    logger.info("Generating Markdown document: %d requirement responses", len(individual_responses))
    
    lines = []
    
    # Title
    title = rfp_title or f"RFP Response - {extraction_result.language.upper()}"
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"**Date:** {datetime.now().strftime('%B %d, %Y')}")
    lines.append("")
    lines.append(f"**Company:** fusionAIx (fusionaix.com)")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Table of Contents
    lines.append("## Table of Contents")
    lines.append("")
    for idx, resp in enumerate(individual_responses, 1):
        req_id = resp.get('requirement_id', f'Requirement {idx}')
        key_phrase = resp.get('key_phrase', '')[:60]
        lines.append(f"{idx}. [{req_id}: {key_phrase}...](#requirement-{idx})")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Company Overview
    lines.append("## Company Overview")
    lines.append("")
    lines.append("fusionAIx is a specialized low-code and AI-driven digital transformation partner focused on modernizing enterprise workflows, improving customer/employee experiences, and accelerating delivery through platform-led automation.")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Solution Requirement Responses
    lines.append("## Solution Requirement Responses")
    lines.append("")
    
    for idx, resp_data in enumerate(individual_responses, 1):
        req_id = resp_data.get('requirement_id', f'Requirement {idx}')
        lines.append(f"### Requirement {idx}: {req_id}")
        lines.append("")
        lines.append(f"**Requirement:** {resp_data.get('requirement_text', '')}")
        lines.append("")
        lines.append("**Response:**")
        lines.append("")
        # Format response text (preserve line breaks)
        response_text = resp_data.get('response', '')
        for line in response_text.split('\n'):
            lines.append(line)
        lines.append("")
        
        # Quality indicator if available
        if resp_data.get('quality'):
            quality = resp_data['quality']
            lines.append("**Quality Assessment:**")
            lines.append(f"- Score: {quality.get('score', 0):.0f}/100")
            lines.append(f"- Completeness: {quality.get('completeness', 'unknown')}")
            lines.append(f"- Relevance: {quality.get('relevance', 'unknown')}")
            if quality.get('issues'):
                lines.append("- Issues:")
                for issue in quality['issues']:
                    lines.append(f"  - {issue}")
            lines.append("")
        
        lines.append("---")
        lines.append("")
    
    markdown_content = "\n".join(lines)
    markdown_bytes = markdown_content.encode('utf-8')
    
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(markdown_bytes)
        logger.info("Markdown saved to: %s", output_path.absolute())
    
    logger.info("Markdown generated: %d bytes", len(markdown_bytes))
    return markdown_bytes

