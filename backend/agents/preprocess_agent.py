from __future__ import annotations

import functools
import json
import logging
import re
from typing import Any, Dict

from backend.llm.client import chat_completion
from backend.models import PreprocessResult
from backend.agents.prompts import PREPROCESS_SYSTEM_PROMPT


logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=256)
def _run_preprocess_agent_cached(document_text: str) -> PreprocessResult:
    logger.info(
        "Preprocess agent: starting (input_chars=%d)",
        len(document_text),
    )

    text_input = document_text[:50000] if len(document_text) > 50000 else document_text

    user_prompt = f"""FULL RAW RFP TEXT (after OCR):
{text_input}
"""

    system_tokens = len(PREPROCESS_SYSTEM_PROMPT) // 4
    user_tokens = len(user_prompt) // 4
    total_input_tokens = system_tokens + user_tokens + 100

    logger.info(
        "Preprocess prompt tokens: system=%d, user=%d, total=%d",
        system_tokens,
        user_tokens,
        total_input_tokens,
    )

    max_output_tokens = max(4000, min(8000, 32769 - total_input_tokens - 1000))

    content = chat_completion(
        model="gpt-5-chat",
        messages=[
            {"role": "system", "content": PREPROCESS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=max_output_tokens,
    )

    def _parse_json_safely(raw: str) -> Dict[str, Any]:
        cleaned = (
            raw.replace("```json", "")
            .replace("```", "")
            .strip()
        )
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            cleaned = match.group(0)
        cleaned = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', cleaned)
        cleaned = re.sub(r",\s*([}\]])", r"\\1", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error("Preprocess agent: failed to parse JSON: %s", str(e))
            logger.debug("Preprocess agent: problematic JSON (first 1500 chars):\n%s", cleaned[:1500])
            raise

    data = _parse_json_safely(content)

    language = data.get("language") or "en"
    cleaned_text = data.get("cleaned_text") or ""
    removed_text = data.get("removed_text") or ""
    key_summary = data.get("key_requirements_summary") or ""
    if isinstance(key_summary, list):
        key_summary = "\n".join(str(item) for item in key_summary if item)
    elif not isinstance(key_summary, str):
        key_summary = str(key_summary) if key_summary else ""

    comparison_agreement = bool(data.get("comparison_agreement", True))
    comparison_notes = data.get("comparison_notes") or ""
    if not isinstance(comparison_notes, str):
        comparison_notes = str(comparison_notes)

    result = PreprocessResult(
        language=language,
        cleaned_text=cleaned_text,
        removed_text=removed_text,
        key_requirements_summary=key_summary,
        comparison_agreement=comparison_agreement,
        comparison_notes=comparison_notes,
    )

    logger.info(
        "Preprocess agent: finished (cleaned_chars=%d, removed_chars=%d)",
        len(result.cleaned_text or ""),
        len(result.removed_text or ""),
    )
    return result


def run_preprocess_agent(document_text: str) -> PreprocessResult:
    cache_info = _run_preprocess_agent_cached.cache_info()
    logger.info(
        "Preprocess agent: cache status (hits=%d, misses=%d, size=%d/%d)",
        cache_info.hits,
        cache_info.misses,
        cache_info.currsize,
        cache_info.maxsize,
    )

    result = _run_preprocess_agent_cached(document_text)
    new_cache_info = _run_preprocess_agent_cached.cache_info()
    if new_cache_info.hits > cache_info.hits:
        logger.info("Preprocess agent: cache HIT - returned cached result")
    else:
        logger.info("Preprocess agent: cache MISS - processed new request")

    return result

