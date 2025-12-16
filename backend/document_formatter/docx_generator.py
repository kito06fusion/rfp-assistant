from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from backend.models import RequirementsResult, ExtractionResult

logger = logging.getLogger(__name__)

try:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    logger.warning("python-docx not available. DOCX export will not work.")


def _add_formatted_text_to_paragraph(para, text: str):
    if not text:
        return
    
    if para.runs:
        para.clear()
    
    parts = []
    last_end = 0
    
    for match in re.finditer(r'\*\*(.*?)\*\*', text):
        if match.start() > last_end:
            parts.append(('normal', text[last_end:match.start()]))
        parts.append(('bold', match.group(1)))
        last_end = match.end()
    
    if last_end < len(text):
        parts.append(('normal', text[last_end:]))
    
    if not parts:
        parts = [('normal', text)]
    
    for fmt_type, content in parts:
        if content:  # Only add non-empty content
            run = para.add_run(content)
            if fmt_type == 'bold':
                run.bold = True


def _parse_markdown_to_docx(doc, text: str):
    if not text:
        return
    
    # Pre-process: remove standalone horizontal rules and clean up
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Skip horizontal rules
        if re.match(r'^---+$', stripped):
            continue
        cleaned_lines.append(line)
    
    lines = cleaned_lines
    i = 0
    in_table = False
    table_rows = []
    header_row = None
    current_table = None
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        if not stripped:
            if in_table and table_rows and current_table:
                in_table = False
                table_rows = []
                header_row = None
                current_table = None
            else:
                doc.add_paragraph()  # Add spacing
            i += 1
            continue
        
        if '|' in stripped and not stripped.startswith('#'):
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if re.match(r'^[\|\s:\-]+$', next_line):
                    cells = [cell.strip() for cell in stripped.split('|') if cell.strip()]
                    if cells:
                        header_row = cells
                        num_cols = len(cells)
                        current_table = doc.add_table(rows=1, cols=num_cols)
                        try:
                            current_table.style = 'Light Grid Accent 1'
                        except:
                            try:
                                current_table.style = 'Grid Table 1 Light'
                            except:
                                pass  # Use default style
                        
                        header_cells = current_table.rows[0].cells
                        for col_idx, cell_text in enumerate(cells):
                            cell = header_cells[col_idx]
                            cell.text = cell_text
                            # Make header bold and set style
                            for paragraph in cell.paragraphs:
                                for run in paragraph.runs:
                                    run.bold = True
                                    try:
                                        run.font.color.rgb = RGBColor(255, 255, 255)  # White text
                                    except:
                                        pass
                            try:
                                tc_pr = cell._element.get_or_add_tcPr()
                                shading = OxmlElement('w:shd')
                                shading.set(qn('w:fill'), '1a5490')
                                shading.set(qn('w:val'), 'clear')
                                tc_pr.append(shading)
                            except Exception as e:
                                logger.warning("Failed to set table header color: %s", e)
                        
                        in_table = True
                        table_rows = []
                        i += 2  # Skip separator line
                        continue
            
            # Regular table row
            if in_table and current_table:
                cells = [cell.strip() for cell in stripped.split('|') if cell.strip()]
                if cells:
                    row = current_table.add_row()
                    for col_idx, cell_text in enumerate(cells):
                        if col_idx < len(row.cells):
                            cell = row.cells[col_idx]
                            # Clear default content and add formatted text
                            cell.text = ""  # Clear first
                            para = cell.paragraphs[0]
                            _add_formatted_text_to_paragraph(para, cell_text)
                    table_rows.append(cells)
                i += 1
                continue
            # Not in table yet, might be starting one
            elif i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if re.match(r'^[\|\s:\-]+$', next_line):
                    cells = [cell.strip() for cell in stripped.split('|') if cell.strip()]
                    if cells:
                        header_row = cells
                        num_cols = len(cells)
                        current_table = doc.add_table(rows=1, cols=num_cols)
                        try:
                            current_table.style = 'Light Grid Accent 1'
                        except:
                            try:
                                current_table.style = 'Grid Table 1 Light'
                            except:
                                pass  # Use default style
                        
                        header_cells = current_table.rows[0].cells
                        for col_idx, cell_text in enumerate(cells):
                            header_cells[col_idx].text = cell_text
                            for paragraph in header_cells[col_idx].paragraphs:
                                if paragraph.runs:
                                    paragraph.runs[0].bold = True
                                    paragraph.runs[0].font.color.rgb = RGBColor(255, 255, 255)  # White text
                            try:
                                tc_pr = header_cells[col_idx]._element.get_or_add_tcPr()
                                shading = OxmlElement('w:shd')
                                shading.set(qn('w:fill'), '1a5490')
                                shading.set(qn('w:val'), 'clear')
                                tc_pr.append(shading)
                            except Exception as e:
                                logger.warning("Failed to set table header color: %s", e)
                        
                        in_table = True
                        table_rows = []
                        i += 2  # Skip separator line
                        continue
            
            _add_text_line(doc, stripped)
            i += 1
            continue
        else:
            if in_table and table_rows and current_table:
                in_table = False
                table_rows = []
                header_row = None
                current_table = None
            
            _add_text_line(doc, stripped)
            i += 1
    
    if in_table and current_table:
        in_table = False
        table_rows = []
        header_row = None
        current_table = None


def _clean_markdown_text(text: str) -> str:
    """Remove markdown formatting from text while preserving content."""
    if not text:
        return text
    # Remove bold markers (but keep the content)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*\*([^*]*)\*\*', r'\1', text)  # Handle empty bold
    # Remove italic markers
    text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'\1', text)
    # Remove code markers
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Remove horizontal rules
    text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)
    # Clean up extra whitespace but preserve sentence structure
    text = re.sub(r'[ \t]+', ' ', text)
    text = text.strip()
    return text


def _capitalize_sentence(text: str) -> str:
    """Capitalize first letter of sentence if needed."""
    if not text:
        return text
    text = text.strip()
    if text and text[0].islower():
        return text[0].upper() + text[1:]
    return text


def _add_text_line(doc, line: str):
    stripped = line.strip()
    if not stripped:
        doc.add_paragraph()
        return
    
    # Skip horizontal rules
    if re.match(r'^---+$', stripped):
        return
    
    # Handle headers - clean markdown first
    if stripped.startswith('#### '):
        header_text = _clean_markdown_text(stripped[5:])
        if header_text:
            doc.add_heading(header_text, 4)
    elif stripped.startswith('### '):
        header_text = _clean_markdown_text(stripped[4:])
        if header_text:
            doc.add_heading(header_text, 3)
    elif stripped.startswith('## '):
        header_text = _clean_markdown_text(stripped[3:])
        if header_text:
            doc.add_heading(header_text, 2)
    elif stripped.startswith('# '):
        header_text = _clean_markdown_text(stripped[2:])
        if header_text:
            doc.add_heading(header_text, 1)
    elif stripped.startswith('- ') or stripped.startswith('* '):
        para = doc.add_paragraph(style='List Bullet')
        content = stripped[2:].strip()
        content = _capitalize_sentence(content)
        _add_formatted_text_to_paragraph(para, content)
    elif re.match(r'^\d+\.\s', stripped):
        para = doc.add_paragraph(style='List Number')
        content = re.sub(r'^\d+\.\s', '', stripped).strip()
        content = _capitalize_sentence(content)
        _add_formatted_text_to_paragraph(para, content)
    else:
        # Regular paragraph - clean and capitalize
        content = _clean_markdown_text(stripped)
        if content:
            # Only capitalize if it looks like the start of a sentence
            # (not if it's already capitalized or starts with a number/special char)
            if content and len(content) > 0 and content[0].islower() and content[0].isalpha():
                content = _capitalize_sentence(content)
            para = doc.add_paragraph()
            _add_formatted_text_to_paragraph(para, content)


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
    
    # Check if this is a structured response
    is_structured = len(individual_responses) == 1 and individual_responses[0].get('requirement_id') == 'STRUCTURED'
    
    if is_structured:
        # For structured responses, extract sections from the response text
        response_text = individual_responses[0].get('response', '')
        toc_para = doc.add_paragraph()
        
        # Extract section headers from response (prioritize ## headers, fallback to ###)
        sections = []
        seen_sections = set()
        for line in response_text.split('\n'):
            stripped = line.strip()
            # Look for main sections (##) first
            if stripped.startswith('## ') and not stripped.startswith('###'):
                section_name = _clean_markdown_text(stripped[3:])
                if section_name and section_name not in seen_sections:
                    sections.append(section_name)
                    seen_sections.add(section_name)
        
        # If no ## headers found, look for ### headers
        if not sections:
            for line in response_text.split('\n'):
                stripped = line.strip()
                if stripped.startswith('### '):
                    section_name = _clean_markdown_text(stripped[4:])
                    if section_name and section_name not in seen_sections:
                        sections.append(section_name)
                        seen_sections.add(section_name)
        
        if sections:
            for idx, section in enumerate(sections, 1):
                toc_para.add_run(f"{idx}. {section}").bold = False
                if idx < len(sections):
                    toc_para.add_run("\n")
        else:
            # Fallback: use key_phrase or first part of response
            key_phrase = individual_responses[0].get('key_phrase', 'Structured Response')
            toc_para.add_run(f"1. {key_phrase}").bold = False
    else:
        # For per-requirement responses
        toc_para = doc.add_paragraph()
        for idx, resp in enumerate(individual_responses, 1):
            req_id = resp.get('requirement_id', f'Requirement {idx}')
            key_phrase = resp.get('key_phrase', '')
            if key_phrase:
                toc_para.add_run(f"{idx}. {req_id}: {key_phrase[:60]}...").bold = False
            else:
                req_text = resp.get('requirement_text', '')[:60]
                toc_para.add_run(f"{idx}. {req_id}: {req_text}...").bold = False
            if idx < len(individual_responses):
                toc_para.add_run("\n")
    
    doc.add_page_break()
    
    doc.add_heading("Company Overview", 1)
    # Use the same detailed overview as PDF generator
    overview_text = """fusionAIx is a specialized low-code and AI-driven digital transformation partner focused on modernizing enterprise workflows, improving customer/employee experiences, and accelerating delivery through platform-led automation. The company was established in 2023, with active entities including a UK-based consultancy (incorporated 3 August 2023) and an India-based technology arm (incorporated 20 July 2023).

With proven capabilities across Pega Constellation, Microsoft Power Platform, and ServiceNow, fusionAIx provides advisory, modernization, implementation, and managed delivery services designed to meet enterprise requirements for scalability, security, and governance.

In the Pega ecosystem, fusionAIx positions itself as a niche Constellation specialist and states it has delivered 20+ Pega Constellation implementations globally. The company also highlights an AI-powered Constellation Center of Excellence aimed at accelerating DX component creation and modernization outcomes.

To speed time-to-value, fusionAIx offers proprietary accelerators and solution components such as fxAgentSDK, fxAIStudio, fxMockUpToView, and fxSmartDCO, alongside Pega Marketplace offerings like fxTranslate for Constellation localization support.

The firm supports clients across industries including insurance, banking/financial services, government, and healthcare, combining platform expertise with structured knowledge transfer to help customers build sustainable, future-ready capabilities."""
    
    # Split into paragraphs for better formatting
    for para_text in overview_text.split('\n\n'):
        if para_text.strip():
            doc.add_paragraph(para_text.strip())
    
    doc.add_page_break()
    
    # Check if this is a structured response
    is_structured = len(individual_responses) == 1 and individual_responses[0].get('requirement_id') == 'STRUCTURED'
    
    if is_structured:
        # For structured responses, the response text already contains all sections with headers
        # No need for "Solution Requirement Responses" heading - sections are in the response
        response_text = individual_responses[0].get('response', '')
        _parse_markdown_to_docx(doc, response_text)
    else:
        # For per-requirement responses, add the section heading
        doc.add_heading("Solution Requirement Responses", 1)
        for idx, resp_data in enumerate(individual_responses, 1):
            req_heading = doc.add_heading(f"Requirement {idx}: {resp_data.get('requirement_id', 'N/A')}", 2)
            
            req_para = doc.add_paragraph()
            req_para.add_run("Requirement: ").bold = True
            req_text = resp_data.get('requirement_text', '')
            if req_text:
                req_para.add_run(_capitalize_sentence(req_text))
            
            resp_heading = doc.add_heading("Response", 3)
            _parse_markdown_to_docx(doc, resp_data.get('response', ''))
            
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

