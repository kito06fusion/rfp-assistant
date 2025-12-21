"""Integration helpers for persisting artifacts in Mem0."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:  # Import lazily so the backend still runs without mem0 installed
    from mem0 import MemoryClient  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    MemoryClient = None  # type: ignore[misc, assignment]

_MEM0_CLIENT: Optional[MemoryClient] = None


def _get_mem0_client() -> Optional[MemoryClient]:
    """Return a singleton Mem0 client if credentials and SDK are available."""

    global _MEM0_CLIENT
    if _MEM0_CLIENT is not None:
        return _MEM0_CLIENT

    if MemoryClient is None:
        logger.debug("mem0 Python SDK not installed; skip Mem0 persistence")
        return None

    api_key = os.getenv("MEM0_API_KEY")
    if not api_key:
        logger.debug("MEM0_API_KEY not set; skip Mem0 persistence")
        return None

    client_kwargs: Dict[str, Any] = {"api_key": api_key}
    org_id = os.getenv("MEM0_ORG_ID")
    project_id = os.getenv("MEM0_PROJECT_ID")
    if org_id:
        client_kwargs["org_id"] = org_id
    if project_id:
        client_kwargs["project_id"] = project_id

    try:
        _MEM0_CLIENT = MemoryClient(**client_kwargs)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Failed to initialize Mem0 client: %s", exc)
        _MEM0_CLIENT = None
    return _MEM0_CLIENT


def _build_messages(preprocess_payload: Dict[str, Any]) -> list[Dict[str, str]]:
    """Create the conversation payload sent to Mem0."""

    summary = preprocess_payload.get("key_requirements_summary") or "RFP preprocess summary"
    cleaned_text = preprocess_payload.get("cleaned_text") or ""
    truncated_cleaned = cleaned_text[:4000]  # prevent oversized payloads

    payload_snapshot = {
        "key_requirements_summary": summary,
        "language": preprocess_payload.get("language"),
        "removed_text_length": len(preprocess_payload.get("removed_text") or ""),
        "cleaned_text_excerpt": truncated_cleaned,
    }

    return [
        {"role": "user", "content": summary},
        {"role": "assistant", "content": json.dumps(payload_snapshot)},
    ]


def store_preprocess_result(source_text: str, preprocess_payload: Dict[str, Any]) -> bool:
    """Persist preprocess output in Mem0, returning True on success."""

    if not source_text:
        logger.debug("No OCR text supplied; skipping Mem0 storage")
        return False

    client = _get_mem0_client()
    if client is None:
        return False

    try:
        user_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Failed to hash OCR text for Mem0 storage: %s", exc)
        return False

    metadata = {
        "stage": "preprocess",
        "language": preprocess_payload.get("language"),
        "source": "rfp-assistant",
    }

    messages = _build_messages(preprocess_payload)
    version = os.getenv("MEM0_MEMORY_VERSION", "v2")

    try:
        client.add(messages, user_id=user_hash, metadata=metadata, version=version)
        return True
    except Exception as exc:  # pragma: no cover - runtime safety
        logger.warning("Mem0 write failed: %s", exc)
        return False
