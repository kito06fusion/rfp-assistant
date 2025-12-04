from __future__ import annotations

import functools
import logging
from dataclasses import dataclass, asdict
from typing import Any, Dict

from backend.llm.client import chat_completion


logger = logging.getLogger(__name__)
EXTRACTION_MODEL = "meta-llama/Llama-3.2-1B-Instruct"


@dataclass
class ExtractionResult:
    translated_text: str
    language: str
    cpv_codes: list[str]
    other_codes: list[str]
    key_requirements_summary: str
    raw_structured: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


EXTRACTION_SYSTEM_PROMPT = """
You are an expert procurement and public-sector tender analyst.

You receive the raw text of a Request for Proposal (RFP) or tender document.

Tasks:
1. Detect the language of the document.
2. If the document is not in English, translate it into clear, professional English.
3. Extract all useful structured information that would help a bidder respond, including:
   - CPV codes or similar classification codes (e.g., UNSPSC, CPV, NAICS, NUTS).
   - Any tender identifiers or reference numbers.
   - Deadlines and key dates.
   - Contract duration and options for extension.
   - Budget / estimated contract value, if mentioned.
   - Mandatory requirements versus optional/desired requirements.
   - Any explicit disqualifying conditions (e.g., late submission, missing documents).
4. Provide a concise summary (10–15 bullet points) of the key solution and response requirements.

Output JSON ONLY, with the following top-level keys:
- language: ISO language name or code (e.g., "en", "fr").
- translated_text: full document text in English.
- cpv_codes: list of strings.
- other_codes: list of strings with code type and value, e.g. "UNSPSC: 12345678".
- key_requirements_summary: markdown bullet list (as a single string).
- metadata: object with any additional fields you consider useful (deadlines, contract value, identifiers, etc.).

Respond with STRICTLY valid JSON. Do not include explanations.
"""


@functools.lru_cache(maxsize=128)
def _run_extraction_agent_cached(document_text: str) -> ExtractionResult:
    """
    Internal cached version of extraction agent.
    Cache key is based on document_text.
    """
    user_prompt = (
        "Here is the raw text of an RFP / tender document:\n\n"
        f"```rfp_text\n{document_text}\n```"
    )

    logger.info("Extraction agent: processing (input_chars=%d)", len(document_text))

    content = chat_completion(
        model=EXTRACTION_MODEL,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=None,
    )

    import json
    import re

    def _parse_json_safely(raw: str) -> dict:
        """
        Robust JSON parser that handles common LLM output issues:
        - Markdown code fences
        - Trailing commas
        - Control characters
        - Truncated JSON
        """
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
            if error_pos:
                before = cleaned[:error_pos]
                after = cleaned[error_pos:]
                pass
            
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
                    except:
                        partial['cpv_codes'] = []
                
                if partial:
                    logger.warning(
                        "Partially parsed JSON, using extracted fields with defaults"
                    )
                    # Do NOT set translated_text here; caller will fall back to OCR text.
                    return {
                        "language": partial.get("language", "en"),
                        "cpv_codes": partial.get("cpv_codes", []),
                    }
            except:
                pass
            
            logger.error("Failed to parse JSON after all cleanup attempts. Error at position %s", error_pos)
            logger.debug("Problematic JSON (first 1500 chars):\n%s", cleaned[:1500])
            raise ValueError(f"LLM extraction agent returned invalid JSON: {str(e)}") from e

    try:
        data = _parse_json_safely(content)
    except ValueError:
        # If parsing fails completely, treat OCR text as translated_text and return empty structure.
        logger.warning(
            "Extraction agent: JSON parsing failed completely, using OCR text as translated_text."
        )
        data = {
            "language": "en",
            "translated_text": document_text,
            "cpv_codes": [],
            "other_codes": [],
            "key_requirements_summary": "",
            "metadata": {},
        }

    translated_text = data.get("translated_text") or document_text

    result = ExtractionResult(
        translated_text="",  # Don't include original text in extraction output
        language=data.get("language", "en"),
        cpv_codes=data.get("cpv_codes", []) or [],
        other_codes=data.get("other_codes", []) or [],
        key_requirements_summary=data.get("key_requirements_summary", ""),
        raw_structured=data.get("metadata", {}) or {},
    )
    logger.info(
        "Extraction agent: finished (lang=%s, cpv=%d, other_codes=%d)",
        result.language,
        len(result.cpv_codes),
        len(result.other_codes),
    )
    return result


def run_extraction_agent(document_text: str) -> ExtractionResult:
    """
    Runs the extraction agent on raw document text.
    Results are cached using LRU cache based on document text.
    """
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
    
    # Check if this was a cache hit
    new_cache_info = _run_extraction_agent_cached.cache_info()
    if new_cache_info.hits > cache_info.hits:
        logger.info("Extraction agent: cache HIT - returned cached result")
    else:
        logger.info("Extraction agent: cache MISS - processed new request")
    
    return result


