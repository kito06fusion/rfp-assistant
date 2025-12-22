from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STORE_PATH = DATA_DIR / "memories.jsonl"


def _append_record(record: Dict[str, Any]) -> bool:
    try:
        with STORE_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Failed to write local memory record: %s", exc)
        return False


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


def _build_requirements_messages(requirements_payload: Dict[str, Any]) -> list[Dict[str, str]]:
    sol = requirements_payload.get("solution_requirements") or []
    resp = requirements_payload.get("response_structure_requirements") or []
    notes = requirements_payload.get("notes") or ""

    def _simplify(reqs: Any, max_items: int = 100) -> list[Dict[str, str]]:
        items: list[Dict[str, str]] = []
        if not isinstance(reqs, list):
            return items
        for raw in reqs[:max_items]:
            if not isinstance(raw, dict):
                continue
            text = str(raw.get("source_text") or "")
            items.append(
                {
                    "id": str(raw.get("id") or ""),
                    "type": str(raw.get("type") or ""),
                    "category": str(raw.get("category") or ""),
                    "source_text": text[:2000],
                }
            )
        return items

    snapshot = {
        "summary": "RFP requirements snapshot",
        "solution_requirements_count": len(sol) if isinstance(sol, list) else 0,
        "response_structure_requirements_count": len(resp) if isinstance(resp, list) else 0,
        "solution_requirements": _simplify(sol),
        "response_structure_requirements": _simplify(resp),
        "notes": str(notes),
    }

    return [
        {"role": "user", "content": "RFP REQUIREMENTS SNAPSHOT"},
        {"role": "assistant", "content": json.dumps(snapshot)},
    ]


def _build_build_query_messages(build_query_payload: Dict[str, Any]) -> list[Dict[str, str]]:
    query_text = str(build_query_payload.get("query_text") or "")
    sol_summary = str(build_query_payload.get("solution_requirements_summary") or "")
    resp_summary = str(build_query_payload.get("response_structure_requirements_summary") or "")

    snapshot = {
        "summary": "RFP build query snapshot",
        "solution_requirements_summary": sol_summary[:4000],
        "response_structure_requirements_summary": resp_summary[:4000],
        "query_preview": query_text[:8000],
    }

    return [
        {"role": "user", "content": "RFP BUILD QUERY SNAPSHOT"},
        {"role": "assistant", "content": json.dumps(snapshot)},
    ]


def store_preprocess_result(source_text: str, preprocess_payload: Dict[str, Any]) -> bool:
    if not source_text:
        logger.debug("Mem0: no OCR text supplied; skipping preprocess storage")
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

    record: Dict[str, Any] = {
        "user_id": user_hash,
        "stage": metadata["stage"],
        "metadata": metadata,
        "messages": messages,
    }
    ok = _append_record(record)
    if ok:
        logger.info("Mem0: stored preprocess record for user_id=%s at %s", user_hash[:12], STORE_PATH)
    else:
        logger.warning("Mem0: failed to store preprocess record for user_id=%s", user_hash[:12])
    return ok


def store_requirements_result(source_text: str, requirements_payload: Dict[str, Any]) -> bool:
    if not source_text:
        logger.debug("Mem0: no essential text supplied; skipping requirements storage")
        return False

    try:
        user_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    except Exception as exc:
        logger.warning("Failed to hash essential text for Mem0 requirements storage: %s", exc)
        return False

    metadata = {
        "stage": "requirements",
        "source": "rfp-assistant",
    }

    messages = _build_requirements_messages(requirements_payload)

    record: Dict[str, Any] = {
        "user_id": user_hash,
        "stage": metadata["stage"],
        "metadata": metadata,
        "messages": messages,
    }
    ok = _append_record(record)
    if ok:
        logger.info("Mem0: stored requirements record for user_id=%s at %s", user_hash[:12], STORE_PATH)
    else:
        logger.warning("Mem0: failed to store requirements record for user_id=%s", user_hash[:12])
    return ok


def store_build_query_result(source_text: str, build_query_payload: Dict[str, Any]) -> bool:
    if not source_text:
        logger.debug("Mem0: no essential text supplied; skipping build-query storage")
        return False

    try:
        user_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    except Exception as exc:
        logger.warning("Failed to hash essential text for Mem0 build query storage: %s", exc)
        return False

    metadata = {
        "stage": "build_query",
        "source": "rfp-assistant",
    }

    messages = _build_build_query_messages(build_query_payload)

    record: Dict[str, Any] = {
        "user_id": user_hash,
        "stage": metadata["stage"],
        "metadata": metadata,
        "messages": messages,
    }
    ok = _append_record(record)
    if ok:
        logger.info("Mem0: stored build-query record for user_id=%s at %s", user_hash[:12], STORE_PATH)
    else:
        logger.warning("Mem0: failed to store build-query record for user_id=%s", user_hash[:12])
    return ok
