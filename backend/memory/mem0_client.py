"""Integration helpers for persisting artifacts in Mem0."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from mem0 import Memory  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    Memory = None  # type: ignore[misc, assignment]

_MEM0_CLIENT: Optional["Memory"] = None


def _get_mem0_client() -> Optional["Memory"]:

    global _MEM0_CLIENT
    if _MEM0_CLIENT is not None:
        return _MEM0_CLIENT

    try:
        _MEM0_CLIENT = Memory()  # type: ignore[call-arg]
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Failed to initialize Mem0 client: %s", exc)
        _MEM0_CLIENT = None
    return _MEM0_CLIENT


def _build_messages(preprocess_payload: Dict[str, Any]) -> list[Dict[str, str]]:

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

    try:
        # Local Mem0 Memory.add; keeps all data on this machine
        client.add(messages, user_id=user_hash, metadata=metadata)
        return True
    except Exception as exc:  # pragma: no cover - runtime safety
        logger.warning("Mem0 write failed: %s", exc)
        return False
