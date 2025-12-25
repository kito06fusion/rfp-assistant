from __future__ import annotations
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Optional
import re

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


logger = logging.getLogger(__name__)


_DATA_URL_RE = re.compile(
    r"data:image/(?P<mime>png|svg(?:\+xml)?);base64,(?P<b64>[A-Za-z0-9+/=\s]+)",
    flags=re.IGNORECASE,
)


def _collect_text_from_response(response) -> str:
    parts = []
    outs = getattr(response, "output", None) or []
    try:
        for item in outs:
            if isinstance(item, dict):
                content = item.get("content")
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict):
                            if "text" in c and isinstance(c["text"], str):
                                parts.append(c["text"])
                            elif c.get("type") == "output_text" and isinstance(c.get("text"), str):
                                parts.append(c.get("text"))
                        elif isinstance(c, str):
                            parts.append(c)
                elif isinstance(content, str):
                    parts.append(content)
            elif isinstance(item, str):
                parts.append(item)
    except Exception:
        parts = []

    if not parts:
        ot = getattr(response, "output_text", None)
        if ot:
            parts.append(ot)

    return "".join(parts)


def _decode_data_url_image(output_text: str, expected_fmt: str) -> Optional[bytes]:
    m = _DATA_URL_RE.search(output_text)
    if not m:
        return None

    mime = m.group("mime").lower()
    if expected_fmt == "png" and mime != "png":
        return None
    if expected_fmt == "svg" and not mime.startswith("svg"):
        return None

    b64 = re.sub(r"\s+", "", m.group("b64"))  # remove whitespace/newlines
    b64 = re.sub(r"[^A-Za-z0-9+/=]", "", b64)

    if (len(b64) % 4) == 1:
        return None

    pad = (-len(b64)) % 4
    if pad:
        b64 += "=" * pad

    try:
        return base64.b64decode(b64)
    except Exception:
        return None


def _is_png(data: bytes) -> bool:
    return bool(data) and data.startswith(b"\x89PNG\r\n\x1a\n")


def _is_jpg(data: bytes) -> bool:
    return bool(data) and data.startswith(b"\xff\xd8")


def _is_svg(data: bytes) -> bool:
    if not data:
        return False
    h = data.lstrip()
    return h.startswith(b"<svg") or h.startswith(b"<?xml") or b"<svg" in h[:500].lower()



def render_mermaid_to_bytes(diagram: str, fmt: str = "png", timeout: int = 30) -> bytes:
    fmt = (fmt or "png").lower()
    if fmt not in ("png", "svg"):
        raise ValueError("fmt must be 'png' or 'svg'")

    api_key = os.environ.get("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key) if api_key else OpenAI()

    tools = [
        {
            "type": "mcp",
            "server_label": "mermaid-mcp",
            "server_description": "A tool to generate and render Mermaid diagrams.",
            "server_url": "https://mcp.mermaid.ai/mcp",
            "require_approval": "never",
        }
    ]

    instruction = f"""Render the following Mermaid diagram to {fmt.upper()}.
If the output is binary (PNG), return the image as base64 only (no extra text).
If the output is SVG, return the raw SVG markup only.
Here is the diagram:
```
{diagram}
```"""

    logger.info("Rendering mermaid diagram via MCP server to %s", fmt)

    try:
        response = client.responses.create(
            model="gpt-5-chat-latest",
            tools=tools,
            input=instruction,
            timeout=timeout,
        )
    except Exception as e:
        logger.exception("MCP mermaid rendering request failed: %s", e)
        raise

    output_text = None
    try:
        output_text = _collect_text_from_response(response)
    except Exception:
        output_text = getattr(response, "output_text", None)

    if not output_text:
        raise RuntimeError("MCP mermaid renderer did not return any textual output")

    output_text = output_text.strip()

    data_decoded = None
    try:
        if fmt == "png":
            m_md = re.search(r"data:image/png;base64,([A-Za-z0-9+/=\s]+)", output_text, flags=re.I)
            if m_md:
                b64 = re.sub(r"\s+", "", m_md.group(1))
                b64 = re.sub(r"[^A-Za-z0-9+/=]", "", b64)
                pad = (-len(b64)) % 4
                if pad:
                    b64 += "=" * pad
                try:
                    data_decoded = base64.b64decode(b64)
                except Exception:
                    data_decoded = None
    except Exception:
        data_decoded = None

    if not data_decoded:
        data_decoded = _decode_data_url_image(output_text, expected_fmt=fmt)
    if data_decoded:
        if fmt == "png":
            if _is_png(data_decoded) or _is_jpg(data_decoded):
                return data_decoded
            if _is_svg(data_decoded):
                logger.warning("MCP returned SVG in data URL while fmt=png (len=%d) - rejecting for DOCX embedding", len(data_decoded))
                data_decoded = None
            else:
                logger.warning("MCP returned non-image bytes in data URL while fmt=png (len=%d) - rejecting for DOCX embedding", len(data_decoded))
                data_decoded = None
        else:
            return data_decoded

    if fmt == "svg":
        if output_text.startswith("<svg"):
            return output_text.encode("utf-8")
        svg_data = _decode_data_url_image(output_text, expected_fmt="svg")
        if svg_data:
            return svg_data
        return output_text.encode("utf-8")

    if output_text.startswith("data:image/png;base64,"):
        b64 = output_text.split(",", 1)[1]
        try:
            decoded = base64.b64decode(b64)
            if _is_png(decoded) or _is_jpg(decoded):
                return decoded
            if _is_svg(decoded):
                logger.warning("MCP returned SVG in explicit data URL while fmt=png (len=%d) - rejecting for DOCX embedding", len(decoded))
            else:
                logger.warning("Decoded explicit data URL but it is not a valid PNG/JPG; allowing Kroki fallback (len=%d)", len(decoded))
        except Exception as e:
            logger.warning("Failed to decode base64 PNG from data URL: %s", e)

    m = re.search(r"```(?:\w+)?\s*([A-Za-z0-9+/=\s]+?)\s*```", output_text, flags=re.DOTALL)
    candidate = None
    if m:
        candidate = m.group(1)

    if not candidate:
        b64_subs = re.findall(r"[A-Za-z0-9+/]{80,}={0,2}", output_text)
        if b64_subs:
            candidate = max(b64_subs, key=len)

    if not candidate:
        stripped = re.sub(r"[^A-Za-z0-9+/=]", "", output_text)
        if len(stripped) >= 64:
            candidate = stripped

    if not candidate:
        preview = output_text[:1000].replace('\n', '\\n')
        logger.warning("No base64-like substring found in MCP response for PNG output. Will allow Kroki fallback. Preview: %s", preview)
        return None

    candidate = re.sub(r"\s+", "", candidate)
    candidate = re.sub(r"[^A-Za-z0-9+/=]", "", candidate)

    pad = (-len(candidate)) % 4
    if pad:
        candidate += "=" * pad

    logger.debug("Attempting to decode base64 PNG candidate (len=%d) ...", len(candidate))
    try:
        decoded = base64.b64decode(candidate)
    except Exception as e:
        logger.warning("Failed to decode base64 PNG candidate from MCP response; allowing Kroki fallback: %s", e)
        return None

    if _is_png(decoded) or _is_jpg(decoded):
        return decoded
    if _is_svg(decoded):
        logger.warning("MCP returned SVG bytes when PNG was requested (len=%d) - rejecting for DOCX embedding", len(decoded))
        return None

    logger.warning("Decoded bytes are not a recognized PNG/JPG/SVG; allowing Kroki fallback (len=%d, head=%r)", len(decoded), decoded[:64])
    return None
