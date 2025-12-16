"""
DOCX Generator for RFP Responses

Generates Microsoft Word (.docx) format documents.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from backend.models import RequirementsResult, ExtractionResult

logger = logging.getLogger(__name__)

try:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    logger.warning("python-docx not available. DOCX export will not work.")


def generate_rfp_docx(
    individual_responses: List[Dict[str, Any]],
    requirements_result: RequirementsResult,
    extraction_result: ExtractionResult,
    rfp_title: Optional[str] = None,
    output_path: Optional[Path] = None,
) -> bytes:
    if not DOCX_AVAILABLE:
        raise ImportError("python-docx is not installed. Install it with: pip install python-docx")
    
    logger.info("Generating DOCX document: %d requirement responses", len(individual_responses))
    
    doc = Document()
    
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Calibri'
    font.size = Pt(11)
    
    title_para = doc.add_heading(rfp_title or f"RFP Response - {extraction_result.language.upper()}", 0)
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    date_para = doc.add_paragraph(datetime.now().strftime("%B %d, %Y"))
    date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    company_para = doc.add_paragraph("fusionAIx")
    company_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    website_para = doc.add_paragraph("fusionaix.com")
    website_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    doc.add_page_break()
    
    doc.add_heading("Table of Contents", 1)
    toc_para = doc.add_paragraph()
    for idx, resp in enumerate(individual_responses, 1):
        toc_para.add_run(f"{idx}. {resp.get('requirement_id', f'Requirement {idx}')}: {resp.get('key_phrase', '')[:60]}...").bold = False
    
    doc.add_page_break()
    
    doc.add_heading("Company Overview", 1)
    overview_text = """fusionAIx is a specialized low-code and AI-driven digital transformation partner focused on modernizing enterprise workflows, improving customer/employee experiences, and accelerating delivery through platform-led automation."""
    doc.add_paragraph(overview_text)
    
    doc.add_page_break()
    
    doc.add_heading("Solution Requirement Responses", 1)
    
    for idx, resp_data in enumerate(individual_responses, 1):
        req_heading = doc.add_heading(f"Requirement {idx}: {resp_data.get('requirement_id', 'N/A')}", 2)
        
        req_para = doc.add_paragraph()
        req_para.add_run("Requirement: ").bold = True
        req_para.add_run(resp_data.get('requirement_text', ''))
        
        resp_heading = doc.add_heading("Response", 3)
        resp_para = doc.add_paragraph(resp_data.get('response', ''))
        
        if resp_data.get('quality'):
            quality = resp_data['quality']
            quality_para = doc.add_paragraph()
            quality_para.add_run(f"Quality Score: {quality.get('score', 0):.0f}/100 | ").bold = True
            quality_para.add_run(f"Completeness: {quality.get('completeness', 'unknown')} | ")
            quality_para.add_run(f"Relevance: {quality.get('relevance', 'unknown')}")
        
        doc.add_paragraph()  # Spacing
    
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path))
        logger.info("DOCX saved to: %s", output_path.absolute())
        return output_path.read_bytes()
    else:
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp:
            doc.save(tmp.name)
            tmp_path = Path(tmp.name)
            bytes_data = tmp_path.read_bytes()
            tmp_path.unlink()
            logger.info("DOCX generated: %d bytes (in memory)", len(bytes_data))
            return bytes_data

