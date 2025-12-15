from __future__ import annotations

import functools
import json
import logging
import re
from typing import Any, Dict

from backend.llm.client import chat_completion
from backend.models import ExtractionResult


logger = logging.getLogger(__name__)
EXTRACTION_MODEL = "gpt-5-chat"


EXTRACTION_SYSTEM_PROMPT = """Extract RFP info. Output JSON:
- language: ISO code (e.g., 'en')
- translated_text: English text
- cpv_codes: array (only if explicitly written)
- other_codes: array (only if written, format "TYPE: VALUE")
- key_requirements_summary: 10-15 bullet points

Rules: Extract only what's written. No inventing codes/dates. No metadata."""

@functools.lru_cache(maxsize=512)
def _run_extraction_agent_cached(document_text: str) -> ExtractionResult:
    doc_text = document_text[:15000] if len(document_text) > 15000 else document_text
    user_prompt = f"RFP:\n{doc_text}\n\nExtract. JSON only. No inventing."
    logger.info("Extraction agent: processing (input_chars=%d)", len(document_text))
    system_tokens = len(EXTRACTION_SYSTEM_PROMPT) // 4
    user_tokens = len(user_prompt) // 4
    total_input_tokens = system_tokens + user_tokens + 100
    logger.info("Extraction prompt tokens: system=%d, user=%d, total=%d", system_tokens, user_tokens, total_input_tokens)
    max_output_tokens = max(3000, min(8000, 32769 - total_input_tokens - 1000))
    content = chat_completion(
        model=EXTRACTION_MODEL,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=max_output_tokens,
    )

    def _parse_json_safely(raw: str) -> dict:
        cleaned = (
            raw.replace("```json", "")
            .replace("```", "")
            .strip()
        )
        cleaned = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', cleaned)       
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            cleaned = match.group(0)        
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)        
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            error_pos = getattr(e, 'pos', None)          
            try:
                partial = {}
                lang_match = re.search(r'"language"\s*:\s*"([^"]+)"', cleaned)
                if lang_match:
                    partial['language'] = lang_match.group(1)
                cpv_match = re.search(r'"cpv_codes"\s*:\s*\[(.*?)\]', cleaned, flags=re.DOTALL)
                if cpv_match:
                    try:
                        cpv_str = '[' + cpv_match.group(1) + ']'
                        partial['cpv_codes'] = json.loads(cpv_str)
                    except (json.JSONDecodeError, ValueError):
                        partial['cpv_codes'] = []       
                if partial:
                    logger.warning(
                        "Partially parsed JSON, using extracted fields with defaults"
                    )
                    return {
                        "language": partial.get("language", "en"),
                        "cpv_codes": partial.get("cpv_codes", []),
                    }
            except Exception:
                pass
            logger.error("Failed to parse JSON after all cleanup attempts. Error at position %s", error_pos)
            logger.debug("Problematic JSON (first 1500 chars):\n%s", cleaned[:1500])
            raise ValueError(f"LLM extraction agent returned invalid JSON: {str(e)}") from e
    try:
        data = _parse_json_safely(content)
    except ValueError:
        logger.warning(
            "Extraction agent: JSON parsing failed completely, using OCR text as translated_text."
        )
        data = {
            "language": "en",
            "translated_text": document_text,
            "cpv_codes": [],
            "other_codes": [],
            "key_requirements_summary": "",
        }

    def _filter_suspicious_codes(codes: list) -> list:
        filtered = []
        for code in codes:
            if not code or not isinstance(code, str):
                continue
            code_str = str(code).strip()
            if not code_str:
                continue
            code_lower = code_str.lower()
            if any(prefix in code_lower for prefix in ['cpv', 'unspsc', 'naics', 'nuts', 'code:', 'code ', 'classification']):
                filtered.append(code_str)
                continue
            if code_str.isdigit() and len(code_str) >= 6:
                logger.warning(
                    "Extraction agent: Filtered out suspicious standalone numeric code (likely hallucination): %s. "
                    "Real codes should have prefixes like 'CPV' or 'UNSPSC'.",
                    code_str
                )
                continue
            filtered.append(code_str)
        return filtered
    cpv_codes = _filter_suspicious_codes(data.get("cpv_codes", []) or [])
    other_codes_raw = data.get("other_codes", []) or []
    other_codes = []
    for code in other_codes_raw:
        if not code or not isinstance(code, str):
            continue
        code_str = str(code).strip()
        if code_str.lower() in ["type: value", "type:value", "type : value"]:
            logger.warning("Extraction agent: Filtered out placeholder 'other_code': %s", code_str)
            continue
        if ":" in code_str and not code_str.lower().startswith("type:"):
            other_codes.append(code_str)
        elif code_str and code_str.lower() not in ["type: value", "type:value"]:
            other_codes.append(code_str)
    key_requirements_summary = data.get("key_requirements_summary", "")
    if isinstance(key_requirements_summary, list):
        key_requirements_summary = "\n".join(str(item) for item in key_requirements_summary)
    elif not isinstance(key_requirements_summary, str):
        key_requirements_summary = str(key_requirements_summary) if key_requirements_summary else ""
    raw_structured = data.get("metadata", {}) or {}
    if raw_structured:
        logger.warning("Extraction agent: metadata field found and will be ignored. Do not include metadata in extraction results.")
        raw_structured = {}
    result = ExtractionResult(
        translated_text="",
        language=data.get("language", "en"),
        cpv_codes=cpv_codes,
        other_codes=other_codes,
        key_requirements_summary=key_requirements_summary,
        raw_structured=raw_structured,
    )
    logger.info(
        "Extraction agent: finished (lang=%s, cpv=%d, other_codes=%d)",
        result.language,
        len(result.cpv_codes),
        len(result.other_codes),
    )
    return result

def run_extraction_agent(document_text: str) -> ExtractionResult:
    cache_info = _run_extraction_agent_cached.cache_info()
    logger.info(
        "Extraction agent: starting (input_chars=%d, cache_hits=%d, cache_misses=%d, cache_size=%d/%d)",
        len(document_text),
        cache_info.hits,
        cache_info.misses,
        cache_info.currsize,
        cache_info.maxsize,
    )

    result = _run_extraction_agent_cached(document_text)
    new_cache_info = _run_extraction_agent_cached.cache_info()
    if new_cache_info.hits > cache_info.hits:
        logger.info("Extraction agent: cache HIT - returned cached result")
    else:
        logger.info("Extraction agent: cache MISS - processed new request")

    return result


