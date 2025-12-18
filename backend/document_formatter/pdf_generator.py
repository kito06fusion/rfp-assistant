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
    "website": "www.fusionaix.com",
    "logo_path": "image.png",
    "overview": """At fusionAIx, we believe that the future of digital transformation lies in the seamless blend of low-code platforms and artificial intelligence. Our core team brings together decades of implementation experience, domain expertise, and a passion for innovation. We partner with enterprises to reimagine processes, accelerate application delivery, and unlock new levels of efficiency. We help businesses scale smarter, faster, and with greater impact.

With a collaborative spirit and a commitment to excellence, our team transforms complex challenges into intelligent, practical solutions. fusionAIx is not just about technology—it's about empowering people, industries, and enterprises to thrive in a digital-first world.

We are proud to be officially recognized as a Great Place To Work® Certified Company for 2025–26, reflecting our commitment to a culture built on trust, innovation, and people-first values.

fusionAIx delivers tailored solutions that blend AI and automation to drive measurable results across industries. We are a niche Pega partner with 20+ successful Pega Constellation implementations across the globe. As Constellation migration experts, we focus on pattern-based development with Constellation, enabling faster project go-lives than traditional implementation approaches.

Our proven capabilities span three core technology platforms: Pega Constellation, Microsoft Power Platform, and ServiceNow. Through these platforms, we provide comprehensive services including Low Code/No Code development, Digital Process Transformation, and AI & Data solutions.

To accelerate time-to-value, fusionAIx offers proprietary accelerators and solution components including fxAgentSDK, fxAIStudio, fxMockUpToView, and fxSmartDCO. These tools enable rapid development, intelligent automation, and streamlined project delivery.

We support clients across diverse industries including Insurance, Banking & Finance, Government & Public Sector, Automotive & Fleet Management, and Travel & Tourism, combining platform expertise with structured knowledge transfer to help customers build sustainable, future-ready capabilities."""
}


def generate_rfp_pdf(
    individual_responses: List[Dict[str, Any]],
    requirements_result: RequirementsResult,
    extraction_result: ExtractionResult,
    rfp_title: Optional[str] = None,
    output_path: Optional[Path] = None,
) -> bytes:
    logger.info(
        "Generating PDF document: %d requirement responses",
        len(individual_responses),
    )
    
    template_dir = Path(__file__).parent.parent / "templates"
    static_dir = Path(__file__).parent.parent / "static"
    project_root = Path(__file__).parent.parent.parent
    
    def format_response_text(text: str) -> str:
        if not text:
            return ""
        
        text = re.sub(r'^#### (.*?)$', r'<h4>\1</h4>', text, flags=re.MULTILINE)
        text = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.*?)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
        
        text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
        
        lines = text.split('\n')
        formatted_lines = []
        in_table = False
        table_rows = []
        header_row = None
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            if not stripped:
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
                    in_table = False
                    table_rows = []
                    header_row = None
                formatted_lines.append('')
                i += 1
                continue
            
            if '|' in stripped and not stripped.startswith('#'):
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if re.match(r'^[\|\s:\-]+$', next_line):
                        cells = [cell.strip() for cell in stripped.split('|') if cell.strip()]
                        if cells:
                            header_row = cells
                            i += 2
                            in_table = True
                            table_rows = []
                            continue
                
                if in_table:
                    cells = [cell.strip() for cell in stripped.split('|') if cell.strip()]
                    if cells:
                        table_rows.append(cells)
                    i += 1
                    continue
                elif i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if re.match(r'^[\|\s:\-]+$', next_line):
                        cells = [cell.strip() for cell in stripped.split('|') if cell.strip()]
                        if cells:
                            header_row = cells
                            i += 2
                            in_table = True
                            table_rows = []
                            continue
                
                formatted_lines.append(stripped)
                i += 1
                continue
            else:
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
                    in_table = False
                    table_rows = []
                    header_row = None
                
                formatted_lines.append(stripped)
                i += 1
        
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
        
        lines = text.split('\n')
        formatted_lines = []
        in_list = False
        list_type = None
        
        for line in lines:
            stripped = line.strip()
            
            if not stripped:
                if in_list:
                    formatted_lines.append(f'</{list_type}>')
                    in_list = False
                    list_type = None
                continue
            
            if stripped.startswith('<h'):
                if in_list:
                    formatted_lines.append(f'</{list_type}>')
                    in_list = False
                    list_type = None
                formatted_lines.append(stripped)
                continue
            
            if stripped.startswith('- ') or stripped.startswith('* '):
                if not in_list or list_type != 'ul':
                    if in_list:
                        formatted_lines.append(f'</{list_type}>')
                    formatted_lines.append('<ul>')
                    in_list = True
                    list_type = 'ul'
                content = stripped[2:].strip()
                formatted_lines.append(f'<li>{content}</li>')
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
            else:
                if in_list:
                    formatted_lines.append(f'</{list_type}>')
                    in_list = False
                    list_type = None
                if not stripped.startswith('<'):
                    formatted_lines.append(f'<p>{stripped}</p>')
                else:
                    formatted_lines.append(stripped)
        
        if in_list:
            formatted_lines.append(f'</{list_type}>')
        
        result = '\n'.join(formatted_lines)
        result = re.sub(r'(<br>\s*){3,}', '<br><br>', result)
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
