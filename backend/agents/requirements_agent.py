from __future__ import annotations

import functools
import json
import logging
import re
from typing import Any, Dict

from backend.llm.client import chat_completion
from backend.models import RequirementItem, RequirementsResult


logger = logging.getLogger(__name__)
REQUIREMENTS_MODEL = "gpt-5-chat"


REQUIREMENTS_SYSTEM_PROMPT = """
You are an RFP requirements analyst. Your ONLY job is to SORT all requirements in the RFP text into two categories. You MUST NOT filter, skip, or decide importance - you must extract ALL requirements.

1. solution_requirements: What the buyer wants (functional, technical, security, SLA, performance, etc.)
2. response_structure_requirements: How to respond (format, language, page limits, submission method, structure, etc.)

CRITICAL RULES:
- Extract ALL requirements from the text - do NOT skip any requirement, even if it seems minor or redundant
- Do NOT decide if a requirement is important or not - extract ALL of them
- Do NOT filter out requirements - your job is ONLY to sort them into the two categories
- If a requirement could fit in both categories, put it in solution_requirements

For each requirement:
- id: short identifier (e.g., "SOL-ARCH-01", "RESP-FORMAT-01")
- type: "mandatory", "optional", or "unspecified" (based on explicit language in the text, not your judgment)
- source_text: COMPLETE original text from RFP (verbatim, all paragraphs, all details - DO NOT summarize)
- normalized_text: concise summary for quick reference
- category: tag (e.g., "Architecture", "Security", "Submission-Format")

CRITICAL: source_text must be the FULL original text verbatim. Extract ALL requirements - completeness is more important than filtering.

Output JSON: solution_requirements (list), response_structure_requirements (list), notes (string). Valid JSON only.
"""

@functools.lru_cache(maxsize=128)
def _run_requirements_agent_cached(essential_text: str, structured_info_json: str) -> RequirementsResult:
    structured_info = json.loads(structured_info_json) if structured_info_json else {}
    user_prompt = (
        f"Scoped RFP text:\n\n{essential_text}\n\n"
        f"Structured info: {structured_info}\n\n"
        "Extract ALL requirements from the text. Do NOT skip any requirements. Your job is ONLY to sort them into solution_requirements or response_structure_requirements. Extract every requirement you find, even if it seems minor or redundant. source_text must be COMPLETE original text verbatim (all paragraphs, all details)."
    )
    logger.info(
        "Requirements agent: processing (essential_chars=%d, has_structured=%s)",
        len(essential_text),
        bool(structured_info),
    )
    estimated_input_tokens = len(user_prompt) // 4 + len(REQUIREMENTS_SYSTEM_PROMPT) // 4 + 500  # +500 for overhead
    max_output_tokens = max(4000, min(10000, 32769 - estimated_input_tokens - 1000))  # Reduced to 10000 to avoid timeouts
    content = chat_completion(
        model=REQUIREMENTS_MODEL,
        messages=[
            {"role": "system", "content": REQUIREMENTS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=max_output_tokens,
    )
    logger.debug("Requirements agent: Raw LLM response length: %d chars", len(content))
    logger.debug("Requirements agent: Raw LLM response (first 500 chars): %s", content[:500])
    logger.debug("Requirements agent: Raw LLM response (last 500 chars): %s", content[-500:] if len(content) > 500 else content)

    def _parse_json_safely(raw: str) -> dict:
        cleaned = (
            raw.replace("```json", "")
            .replace("```", "")
            .strip()
        )
        cleaned = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', cleaned)
        matches = list(re.finditer(r"\{.*?\}", cleaned, flags=re.DOTALL))
        if matches:
            start_pos = min(m.start() for m in matches)
            end_pos = max(m.end() for m in matches)
            brace_count = 0
            start_idx = cleaned.find('{')
            if start_idx >= 0:
                for i in range(start_idx, len(cleaned)):
                    if cleaned[i] == '{':
                        brace_count += 1
                    elif cleaned[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            cleaned = cleaned[start_idx:i+1]
                            break
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)  # Trailing commas
        
        def fix_string_value(match):
            content = match.group(1)
            content = content.replace(chr(10), '\\n').replace(chr(13), '\\r').replace(chr(9), '\\t')
            return f'": "{content}"'
        cleaned = re.sub(r'":\s*"([^"]*(?:\\.[^"]*)*)"', fix_string_value, cleaned)

        try:
            parsed = json.loads(cleaned)
            logger.debug("Requirements agent: Successfully parsed JSON. Top-level keys: %s", list(parsed.keys()) if isinstance(parsed, dict) else "not a dict")
            return parsed
        except json.JSONDecodeError as e:
            error_pos = getattr(e, 'pos', None)
            logger.error("Requirements agent: failed to parse JSON at position %s: %s", error_pos, str(e))
            logger.error("Requirements agent: Problematic JSON (first 2000 chars): %s", cleaned[:2000])
            logger.error("Requirements agent: Problematic JSON (last 500 chars): %s", cleaned[-500:] if len(cleaned) > 500 else cleaned)       
            try:
                partial = {}
                sol_start = cleaned.find('"solution_requirements"')
                if sol_start >= 0:
                    bracket_start = cleaned.find('[', sol_start)
                    if bracket_start >= 0:
                        bracket_count = 0
                        array_start = bracket_start
                        for i in range(bracket_start, len(cleaned)):
                            if cleaned[i] == '[':
                                bracket_count += 1
                            elif cleaned[i] == ']':
                                bracket_count -= 1
                                if bracket_count == 0:
                                    array_content = cleaned[array_start+1:i]
                                    try:
                                        if array_content.strip():
                                            partial['solution_requirements'] = json.loads('[' + array_content + ']')
                                        else:
                                            partial['solution_requirements'] = []
                                    except Exception as parse_err:
                                        logger.warning("Requirements agent: Failed to parse solution_requirements array: %s", parse_err)
                                        partial['solution_requirements'] = []
                                    break
                        else:
                            partial['solution_requirements'] = []
                    else:
                        partial['solution_requirements'] = []
                else:
                    partial['solution_requirements'] = []
                resp_start = cleaned.find('"response_structure_requirements"')
                if resp_start >= 0:
                    bracket_start = cleaned.find('[', resp_start)
                    if bracket_start >= 0:
                        bracket_count = 0
                        array_start = bracket_start
                        for i in range(bracket_start, len(cleaned)):
                            if cleaned[i] == '[':
                                bracket_count += 1
                            elif cleaned[i] == ']':
                                bracket_count -= 1
                                if bracket_count == 0:
                                    array_content = cleaned[array_start+1:i]
                                    try:
                                        if array_content.strip():
                                            partial['response_structure_requirements'] = json.loads('[' + array_content + ']')
                                        else:
                                            partial['response_structure_requirements'] = []
                                    except Exception as parse_err:
                                        logger.warning("Requirements agent: Failed to parse response_structure_requirements array: %s", parse_err)
                                        partial['response_structure_requirements'] = []
                                    break
                        else:
                            partial['response_structure_requirements'] = []
                    else:
                        partial['response_structure_requirements'] = []
                else:
                    partial['response_structure_requirements'] = []
                
                if partial:
                    logger.warning("Requirements agent: Partially parsed JSON, using extracted fields")
                    logger.warning("Requirements agent: solution_requirements: %d items, response_structure_requirements: %d items",
                                 len(partial.get('solution_requirements', [])),
                                 len(partial.get('response_structure_requirements', [])))
                    partial.setdefault('solution_requirements', [])
                    partial.setdefault('response_structure_requirements', [])
                    partial.setdefault('notes', '')
                    return partial
            except Exception as parse_exc:
                logger.error("Requirements agent: Partial extraction also failed: %s", parse_exc)
            logger.error("Requirements agent: Raw LLM response (first 3000 chars): %s", raw[:3000])
            raise ValueError(f"LLM requirements agent returned invalid JSON: {str(e)}") from e
    try:
        data = _parse_json_safely(content)
        logger.debug("Requirements agent: Parsed JSON successfully. Keys: %s", list(data.keys()))
        logger.debug("Requirements agent: solution_requirements count: %d, response_structure_requirements count: %d", 
                     len(data.get("solution_requirements", []) or []), 
                     len(data.get("response_structure_requirements", []) or []))
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Requirements agent: JSON parsing failed: %s", e)
        logger.error("Requirements agent: Raw response (first 2000 chars): %s", content[:2000])
        raise
    solution_reqs = []
    solution_raw = data.get("solution_requirements", []) or []
    logger.info("Requirements agent: Processing %d solution requirements", len(solution_raw))
    for idx, req_dict in enumerate(solution_raw):
        try:
            solution_reqs.append(RequirementItem(**req_dict))
        except Exception as e:
            logger.warning("Failed to parse solution requirement #%d: %s, error: %s", idx, req_dict, e)
            logger.debug("Failed requirement dict keys: %s", list(req_dict.keys()) if isinstance(req_dict, dict) else "not a dict")
    response_reqs = []
    response_raw = data.get("response_structure_requirements", []) or []
    logger.info("Requirements agent: Processing %d response structure requirements", len(response_raw))
    for idx, req_dict in enumerate(response_raw):
        try:
            response_reqs.append(RequirementItem(**req_dict))
        except Exception as e:
            logger.warning("Failed to parse response structure requirement #%d: %s, error: %s", idx, req_dict, e)
            logger.debug("Failed requirement dict keys: %s", list(req_dict.keys()) if isinstance(req_dict, dict) else "not a dict")
    result = RequirementsResult(
        solution_requirements=solution_reqs,
        response_structure_requirements=response_reqs,
        notes=data.get("notes", ""),
    )
    logger.info(
        "Requirements agent: finished (solution=%d, response_structure=%d)",
        len(result.solution_requirements),
        len(result.response_structure_requirements),
    )
    return result

def run_requirements_agent(
    essential_text: str,
    structured_info: Dict[str, Any],
) -> RequirementsResult:
    structured_info_json = json.dumps(structured_info, sort_keys=True) if structured_info else "{}"
    cache_info = _run_requirements_agent_cached.cache_info()
    logger.info(
        "Requirements agent: starting (essential_chars=%d, has_structured=%s, cache_hits=%d, cache_misses=%d, cache_size=%d/%d)",
        len(essential_text),
        bool(structured_info),
        cache_info.hits,
        cache_info.misses,
        cache_info.currsize,
        cache_info.maxsize,
    )
    result = _run_requirements_agent_cached(essential_text, structured_info_json)
    new_cache_info = _run_requirements_agent_cached.cache_info()
    if new_cache_info.hits > cache_info.hits:
        logger.info("Requirements agent: cache HIT - returned cached result")
    else:
        logger.info("Requirements agent: cache MISS - processed new request")

    return result


