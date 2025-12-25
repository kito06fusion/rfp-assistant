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

#function to collect textual content from an OpenAI/MCP response object
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

#function to decode a data URL image (png/svg) into bytes if present
def _decode_data_url_image(output_text: str, expected_fmt: str) -> Optional[bytes]:
    m = _DATA_URL_RE.search(output_text)
    if not m:
        return None

    mime = m.group("mime").lower()
    if expected_fmt == "png" and mime != "png":
        return None
    if expected_fmt == "svg" and not mime.startswith("svg"):
        return None

    b64 = re.sub(r"\s+", "", m.group("b64"))
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

#function to check if bytes represent a PNG image
def _is_png(data: bytes) -> bool:
    return bool(data) and data.startswith(b"\x89PNG\r\n\x1a\n")

#function to check if bytes represent a JPEG image
def _is_jpg(data: bytes) -> bool:
    return bool(data) and data.startswith(b"\xff\xd8")

#function to heuristically check if bytes look like SVG markup
def _is_svg(data: bytes) -> bool:
    if not data:
        return False
    h = data.lstrip()
    return h.startswith(b"<svg") or h.startswith(b"<?xml") or b"<svg" in h[:500].lower()

#function to render a mermaid diagram to bytes using MCP or fall back strategies
def render_mermaid_to_bytes(diagram: str, fmt: str = "png", timeout: int = 90) -> Optional[bytes]:
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
If PNG: return exactly one line in the form `data:image/png;base64,<BASE64>` and nothing else.
If SVG: return the raw SVG markup only (no surrounding commentary).
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
        logger.warning("MCP mermaid renderer returned no textual output")
        return None

    output_text = output_text.strip()

    if fmt == "png":
        m = re.search(r"data:image/png;base64,([A-Za-z0-9+/=\s]+)", output_text, flags=re.I)
        if not m:
            logger.debug("No explicit PNG data URL found in MCP response; will fall back to Kroki")
            return None

        b64 = re.sub(r"\s+", "", m.group(1))
        b64 = re.sub(r"[^A-Za-z0-9+/=]", "", b64)
        pad = (-len(b64)) % 4
        if pad:
            b64 += "=" * pad

        try:
            decoded = base64.b64decode(b64)
        except Exception as e:
            logger.warning("Failed to decode PNG base64 from MCP response: %s", e)
            return None

        if _is_png(decoded) or _is_jpg(decoded):
            return decoded
        if _is_svg(decoded):
            logger.warning("MCP returned SVG bytes in PNG data URL; rejecting and falling back")
            return None

        logger.warning("Decoded bytes are not a recognized PNG/JPG; rejecting and falling back")
        return None

    if fmt == "svg":
        if output_text.startswith("<svg") or output_text.lstrip().startswith("<?xml"):
            return output_text.encode("utf-8")
        svg_data = _decode_data_url_image(output_text, expected_fmt="svg")
        if svg_data:
            return svg_data
        return output_text.encode("utf-8")