from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import List, Union

from PIL import Image  # type: ignore

from backend.llm.client import chat_completion_with_vision


logger = logging.getLogger(__name__)

PathLike = Union[str, Path]

TEXT_EXTRACTION_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"


def _pdf_to_images(pdf_path: Path) -> List[Image.Image]:
    try:
        from pdf2image import convert_from_path  # type: ignore
    except ImportError:
        raise ImportError(
            "pdf2image is required for PDF text extraction. "
            "Install with: pip install pdf2image. "
            "You may also need poppler-utils: brew install poppler (macOS) or apt-get install poppler-utils (Linux)"
        )

    logger.info("Converting PDF to images: %s", pdf_path)
    images = convert_from_path(str(pdf_path), dpi=200)
    logger.info("Converted PDF to %d page images", len(images))
    return images


def _docx_to_images(docx_path: Path) -> List[Image.Image]:
    try:
        from docx2pdf import convert  # type: ignore
        from pdf2image import convert_from_path  # type: ignore
    except ImportError:
        raise ImportError(
            "docx2pdf and pdf2image are required for DOCX text extraction. "
            "Install with: pip install docx2pdf pdf2image. "
            "You may also need poppler-utils: brew install poppler (macOS) or apt-get install poppler-utils (Linux)"
        )

    import tempfile

    logger.info("Converting DOCX to images: %s", docx_path)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
        tmp_pdf_path = Path(tmp_pdf.name)
        try:
            convert(str(docx_path), str(tmp_pdf_path))
            images = convert_from_path(str(tmp_pdf_path), dpi=200)
            logger.info("Converted DOCX to %d page images", len(images))
            return images
        finally:
            try:
                tmp_pdf_path.unlink(missing_ok=True)
            except Exception:
                pass


def _image_to_base64(image: Image.Image) -> str:
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{img_base64}"


def _extract_text_from_images(images: List[Image.Image]) -> str:
    logger.info("Extracting text from %d images using %s", len(images), TEXT_EXTRACTION_MODEL)

    all_text_parts: List[str] = []

    for idx, image in enumerate(images):
        logger.info("Processing page %d/%d", idx + 1, len(images))
        img_base64 = _image_to_base64(image)

        prompt = (
            "Extract ALL text from this document page. "
            "Preserve the structure, formatting, and order of the text as it appears. "
            "Include all headings, paragraphs, lists, tables (as text), and any other textual content. "
            "Do not summarize or skip any text. Return the complete text content of this page."
        )

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": img_base64},
                    },
                ],
            }
        ]

        page_text = chat_completion_with_vision(
            model=TEXT_EXTRACTION_MODEL,
            messages=messages,
            temperature=0.1,
            max_tokens=None,
        )

        all_text_parts.append(page_text)
        logger.debug("Page %d: extracted %d chars", idx + 1, len(page_text))

    full_text = "\n\n--- Page Break ---\n\n".join(all_text_parts)
    logger.info("Total extracted text: %d chars from %d pages", len(full_text), len(images))
    return full_text


def extract_text_from_file(path: PathLike) -> str:
    p = Path(path)
    suffix = p.suffix.lower()

    if suffix == ".pdf":
        images = _pdf_to_images(p)
    elif suffix in {".docx", ".doc"}:
        images = _docx_to_images(p)
    else:
        raise ValueError(f"Unsupported file type for path: {path}")

    if not images:
        logger.warning("No images generated from file: %s", path)
        return ""

    return _extract_text_from_images(images)


