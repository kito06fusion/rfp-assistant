from __future__ import annotations

from backend.document_formatter.pdf_generator import generate_rfp_pdf

try:
    from backend.document_formatter.docx_generator import generate_rfp_docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    generate_rfp_docx = None

from backend.document_formatter.markdown_generator import generate_rfp_markdown

__all__ = ["generate_rfp_pdf", "generate_rfp_docx", "generate_rfp_markdown"]
