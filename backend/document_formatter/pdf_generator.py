from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

import re
from jinja2 import Environment, FileSystemLoader, select_autoescape

from backend.models import RequirementsResult, ExtractionResult

logger = logging.getLogger(__name__)

COMPANY_INFO = {
    "name": "fusionAIx",
    "website": "fusionaix.com",
    "logo_path": "image.png",
    "overview": """fusionAIx is a specialized low-code and AI-driven digital transformation partner focused on modernizing enterprise workflows, improving customer/employee experiences, and accelerating delivery through platform-led automation. The company was established in 2023, with active entities including a UK-based consultancy (incorporated 3 August 2023) and an India-based technology arm (incorporated 20 July 2023).

With proven capabilities across Pega Constellation, Microsoft Power Platform, and ServiceNow, fusionAIx provides advisory, modernization, implementation, and managed delivery services designed to meet enterprise requirements for scalability, security, and governance.

In the Pega ecosystem, fusionAIx positions itself as a niche Constellation specialist and states it has delivered 20+ Pega Constellation implementations globally. The company also highlights an AI-powered Constellation Center of Excellence aimed at accelerating DX component creation and modernization outcomes.

To speed time-to-value, fusionAIx offers proprietary accelerators and solution components such as fxAgentSDK, fxAIStudio, fxMockUpToView, and fxSmartDCO, alongside Pega Marketplace offerings like fxTranslate for Constellation localization support.

The firm supports clients across industries including insurance, banking/financial services, government, and healthcare, combining platform expertise with structured knowledge transfer to help customers build sustainable, future-ready capabilities."""
}


def generate_rfp_pdf(
    individual_responses: List[Dict[str, Any]],
    requirements_result: RequirementsResult,
    extraction_result: ExtractionResult,
    rfp_title: Optional[str] = None,
    output_path: Optional[Path] = None,
) -> bytes:
    """
    Generate a formatted PDF document from RFP responses.
    
    Args:
        individual_responses: List of individual requirement responses
        requirements_result: RequirementsResult containing all requirements
        extraction_result: ExtractionResult with RFP metadata
        rfp_title: Optional title for the RFP (defaults to extraction-based title)
        output_path: Optional path to save PDF (if None, returns bytes)
    
    Returns:
        PDF bytes if output_path is None, otherwise writes to file
    """
    logger.info(
        "Generating PDF document: %d requirement responses",
        len(individual_responses),
    )
    
    template_dir = Path(__file__).parent.parent / "templates"
    static_dir = Path(__file__).parent.parent / "static"
    project_root = Path(__file__).parent.parent.parent
    
    def format_response_text(text: str) -> str:
        """Convert markdown-style text to HTML, avoiding duplication."""
        if not text:
            return ""
        
        # First, convert headers (process from most specific to least)
        text = re.sub(r'^#### (.*?)$', r'<h4>\1</h4>', text, flags=re.MULTILINE)
        text = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.*?)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
        
        # Convert bold
        text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
        
        # Convert markdown tables to HTML tables
        # Pattern: | Header1 | Header2 | Header3 |
        #          |---------|---------|---------|
        #          | Cell1   | Cell2   | Cell3   |
        lines = text.split('\n')
        formatted_lines = []
        in_table = False
        table_rows = []
        header_row = None
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Handle empty lines - close table if in one
            if not stripped:
                if in_table and table_rows:
                    # Close the table
                    formatted_lines.append('<table>')
                    if header_row:
                        formatted_lines.append('<thead><tr>')
                        for cell in header_row:
                            formatted_lines.append(f'<th>{cell}</th>')
                        formatted_lines.append('</tr></thead>')
                    formatted_lines.append('<tbody>')
                    for row in table_rows:
                        formatted_lines.append('<tr>')
                        for cell in row:
                            formatted_lines.append(f'<td>{cell}</td>')
                        formatted_lines.append('</tr>')
                    formatted_lines.append('</tbody></table>')
                    in_table = False
                    table_rows = []
                    header_row = None
                formatted_lines.append('')
                i += 1
                continue
            
            # Check if this is a table row (contains |)
            if '|' in stripped and not stripped.startswith('#'):
                # Check if next line is a separator (contains --- or ===)
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if re.match(r'^[\|\s:\-]+$', next_line):
                        # This is a header row, next is separator
                        cells = [cell.strip() for cell in stripped.split('|') if cell.strip()]
                        if cells:
                            header_row = cells
                            i += 2  # Skip separator line
                            in_table = True
                            table_rows = []
                            continue
                
                # Regular table row
                if in_table:
                    cells = [cell.strip() for cell in stripped.split('|') if cell.strip()]
                    if cells:
                        table_rows.append(cells)
                    i += 1
                    continue
                # Not in table yet, might be starting one
                elif i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if re.match(r'^[\|\s:\-]+$', next_line):
                        # Starting a new table
                        cells = [cell.strip() for cell in stripped.split('|') if cell.strip()]
                        if cells:
                            header_row = cells
                            i += 2  # Skip separator line
                            in_table = True
                            table_rows = []
                            continue
                
                # Not a table, process normally
                formatted_lines.append(stripped)
                i += 1
                continue
            else:
                # Not a table line
                if in_table and table_rows:
                    # Close the table
                    formatted_lines.append('<table>')
                    if header_row:
                        formatted_lines.append('<thead><tr>')
                        for cell in header_row:
                            formatted_lines.append(f'<th>{cell}</th>')
                        formatted_lines.append('</tr></thead>')
                    formatted_lines.append('<tbody>')
                    for row in table_rows:
                        formatted_lines.append('<tr>')
                        for cell in row:
                            formatted_lines.append(f'<td>{cell}</td>')
                        formatted_lines.append('</tr>')
                    formatted_lines.append('</tbody></table>')
                    in_table = False
                    table_rows = []
                    header_row = None
                
                formatted_lines.append(stripped)
                i += 1
        
        # Close any open table
        if in_table and table_rows:
            formatted_lines.append('<table>')
            if header_row:
                formatted_lines.append('<thead><tr>')
                for cell in header_row:
                    formatted_lines.append(f'<th>{cell}</th>')
                formatted_lines.append('</tr></thead>')
            formatted_lines.append('<tbody>')
            for row in table_rows:
                formatted_lines.append('<tr>')
                for cell in row:
                    formatted_lines.append(f'<td>{cell}</td>')
                formatted_lines.append('</tr>')
            formatted_lines.append('</tbody></table>')
        
        text = '\n'.join(formatted_lines)
        
        # Process lines for lists and paragraphs
        lines = text.split('\n')
        formatted_lines = []
        in_list = False
        list_type = None  # 'ul' or 'ol'
        
        for line in lines:
            stripped = line.strip()
            
            # Skip empty lines (they'll be handled by paragraph spacing)
            if not stripped:
                if in_list:
                    formatted_lines.append(f'</{list_type}>')
                    in_list = False
                    list_type = None
                continue
            
            # Check if line is already a header (from previous processing)
            if stripped.startswith('<h'):
                if in_list:
                    formatted_lines.append(f'</{list_type}>')
                    in_list = False
                    list_type = None
                formatted_lines.append(stripped)
                continue
            
            # Check for bullet list
            if stripped.startswith('- ') or stripped.startswith('* '):
                if not in_list or list_type != 'ul':
                    if in_list:
                        formatted_lines.append(f'</{list_type}>')
                    formatted_lines.append('<ul>')
                    in_list = True
                    list_type = 'ul'
                content = stripped[2:].strip()
                formatted_lines.append(f'<li>{content}</li>')
            # Check for numbered list
            elif re.match(r'^\d+\.\s+', stripped):
                if not in_list or list_type != 'ol':
                    if in_list:
                        formatted_lines.append(f'</{list_type}>')
                    formatted_lines.append('<ol>')
                    in_list = True
                    list_type = 'ol'
                match = re.match(r'^\d+\.\s*(.*)', stripped)
                if match:
                    formatted_lines.append(f'<li>{match.group(1)}</li>')
            # Regular paragraph
            else:
                if in_list:
                    formatted_lines.append(f'</{list_type}>')
                    in_list = False
                    list_type = None
                # Only wrap in <p> if not already HTML
                if not stripped.startswith('<'):
                    formatted_lines.append(f'<p>{stripped}</p>')
                else:
                    formatted_lines.append(stripped)
        
        # Close any open list
        if in_list:
            formatted_lines.append(f'</{list_type}>')
        
        result = '\n'.join(formatted_lines)
        # Clean up excessive breaks
        result = re.sub(r'(<br>\s*){3,}', '<br><br>', result)
        # Remove empty paragraphs
        result = re.sub(r'<p>\s*</p>', '', result)
        return result
    
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(['html', 'xml'])
    )
    env.filters['format_response'] = format_response_text
    
    logo_path = project_root / COMPANY_INFO["logo_path"]
    if not logo_path.exists():
        logger.warning("Logo file not found at %s, using placeholder", logo_path)
        logo_path_str = COMPANY_INFO["logo_path"]
    else:
        logo_path_str = COMPANY_INFO["logo_path"]
    
    if not rfp_title:
        rfp_title = f"RFP Response - {extraction_result.language.upper()}"
        if extraction_result.cpv_codes:
            rfp_title += f" (CPV: {', '.join(extraction_result.cpv_codes[:2])})"
    
    company_info_with_logo = COMPANY_INFO.copy()
    company_info_with_logo["logo_path"] = logo_path_str
    
    context = {
        "company_info": company_info_with_logo,
        "rfp_title": rfp_title,
        "date": datetime.now().strftime("%B %d, %Y"),
        "individual_responses": individual_responses,
        "extraction_result": extraction_result,
    }
    
    template = env.get_template("rfp_document.html")
    html_content = template.render(**context)
    
    css_path = Path(__file__).parent.parent / "static" / "styles" / "document.css"
    
    try:
        from weasyprint import HTML, CSS
    except ImportError as e:
        logger.error(
            "WeasyPrint import failed. Please install system dependencies. "
            "See: https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation"
        )
        raise ImportError(
            "WeasyPrint dependencies not installed. "
            "For Docker: Install GTK libraries. "
            "For local: Follow WeasyPrint installation guide."
        ) from e
    
    html_doc = HTML(string=html_content, base_url=str(project_root))
    css_doc = CSS(filename=str(css_path))
    
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info("Generating PDF and saving to: %s", output_path.absolute())
        html_doc.write_pdf(output_path, stylesheets=[css_doc])
        
        if output_path.exists():
            file_size = output_path.stat().st_size
            logger.info("PDF successfully written to: %s (%d bytes)", output_path.absolute(), file_size)
        else:
            logger.error("PDF file was not created at: %s", output_path.absolute())
            raise FileNotFoundError(f"PDF file was not created at {output_path}")
        
        return output_path.read_bytes()
    else:
        pdf_bytes = html_doc.write_pdf(stylesheets=[css_doc])
        logger.info("PDF generated: %d bytes (in memory)", len(pdf_bytes))
        return pdf_bytes
