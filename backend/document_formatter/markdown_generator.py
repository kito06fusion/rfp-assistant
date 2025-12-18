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
    logger.info("Generating Markdown document: %d requirement responses", len(individual_responses))
    
    lines = []
    
    title = rfp_title or f"RFP Response - {extraction_result.language.upper()}"
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"**Date:** {datetime.now().strftime('%B %d, %Y')}")
    lines.append("")
    lines.append(f"**Company:** fusionAIx (www.fusionaix.com)")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    lines.append("## Table of Contents")
    lines.append("")
    for idx, resp in enumerate(individual_responses, 1):
        req_id = resp.get('requirement_id', f'Requirement {idx}')
        key_phrase = resp.get('key_phrase', '')[:60]
        lines.append(f"{idx}. [{req_id}: {key_phrase}...](#requirement-{idx})")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    lines.append("## Company Overview")
    lines.append("")
    lines.append("At fusionAIx, we believe that the future of digital transformation lies in the seamless blend of low-code platforms and artificial intelligence. Our core team brings together decades of implementation experience, domain expertise, and a passion for innovation. We partner with enterprises to reimagine processes, accelerate application delivery, and unlock new levels of efficiency. We help businesses scale smarter, faster, and with greater impact.")
    lines.append("")
    lines.append("With a collaborative spirit and a commitment to excellence, our team transforms complex challenges into intelligent, practical solutions. fusionAIx is not just about technology—it's about empowering people, industries, and enterprises to thrive in a digital-first world.")
    lines.append("")
    lines.append("We are proud to be officially recognized as a Great Place To Work® Certified Company for 2025–26, reflecting our commitment to a culture built on trust, innovation, and people-first values.")
    lines.append("")
    lines.append("fusionAIx delivers tailored solutions that blend AI and automation to drive measurable results across industries. We are a niche Pega partner with 20+ successful Pega Constellation implementations across the globe. As Constellation migration experts, we focus on pattern-based development with Constellation, enabling faster project go-lives than traditional implementation approaches.")
    lines.append("")
    lines.append("Our proven capabilities span three core technology platforms: Pega Constellation, Microsoft Power Platform, and ServiceNow. Through these platforms, we provide comprehensive services including Low Code/No Code development, Digital Process Transformation, and AI & Data solutions.")
    lines.append("")
    lines.append("To accelerate time-to-value, fusionAIx offers proprietary accelerators and solution components including fxAgentSDK, fxAIStudio, fxMockUpToView, and fxSmartDCO. These tools enable rapid development, intelligent automation, and streamlined project delivery.")
    lines.append("")
    lines.append("We support clients across diverse industries including Insurance, Banking & Finance, Government & Public Sector, Automotive & Fleet Management, and Travel & Tourism, combining platform expertise with structured knowledge transfer to help customers build sustainable, future-ready capabilities.")
    lines.append("")
    lines.append("---")
    lines.append("")
    
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
        response_text = resp_data.get('response', '')
        for line in response_text.split('\n'):
            lines.append(line)
        lines.append("")
        
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

