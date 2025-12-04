from __future__ import annotations

import functools
import json
import logging
import re
from typing import Any, Dict

from backend.llm.client import chat_completion
from backend.models import ExtractionResult


logger = logging.getLogger(__name__)
EXTRACTION_MODEL = "meta-llama/Llama-3.2-1B-Instruct"


EXTRACTION_SYSTEM_PROMPT = """
You are an expert procurement and public-sector tender analyst.

You receive the raw text of a Request for Proposal (RFP) or tender document.

Tasks:
1. Detect the language of the document.
2. If the document is not in English, translate it into clear, professional English.
3. Extract ONLY the information that is explicitly stated in the document. Do NOT invent, guess, or infer information that is not present.

Extract the following information ONLY if it appears in the document text:
   - CPV codes or similar classification codes: ONLY extract codes that are explicitly written in the document (e.g., "CPV 12345678" or "CPV code: 12345678"). 
     * CRITICAL: Do NOT create or invent codes. Only extract codes that are literally written in the document.
     * Do NOT extract placeholder codes like "12345678" unless they are explicitly written in the document.
     * If you see text like "CPV code: [to be filled]" or "CPV: TBD", do NOT extract anything.
     * If no CPV codes are mentioned or only placeholders are mentioned, return an empty list [].
   - Other classification codes: ONLY extract codes that are explicitly written (e.g., UNSPSC, NAICS, NUTS codes). Include the code type and value exactly as written.
     * CRITICAL: Do NOT create or invent codes. Only extract codes that are literally written.
     * If no codes are mentioned or only placeholders are mentioned, return an empty list [].
   - Tender identifiers or reference numbers: ONLY if explicitly stated (e.g., "RFP No: 2024/01").
   - Deadlines and key dates: ONLY if explicitly stated with dates.
   - Contract duration and options for extension: ONLY if explicitly mentioned.
   - Budget / estimated contract value: ONLY if explicitly stated with numbers.
   - Mandatory requirements versus optional/desired requirements: Extract from explicit statements.
   - Disqualifying conditions: ONLY if explicitly stated (e.g., "late submission will result in rejection").
4. Provide a concise summary (10–15 bullet points) of the key solution and response requirements based ONLY on what is stated in the document.

CRITICAL RULES - READ CAREFULLY:
- Extract ONLY information that is explicitly written in the document text.
- Do NOT invent, guess, or create codes that are not present.
- Do NOT extract placeholder codes like "12345678" unless they are explicitly written in the document.
- Do NOT extract generic numbers that look like codes but are not explicitly labeled as codes.
- If a field is not mentioned in the document, return an empty list or empty string.
- For codes: Only include codes that are literally written in the document with their code type (e.g., "CPV 12345678" or "CPV code: 12345678").
- If you see "CPV" or "classification code" mentioned but no actual code numbers, do NOT create fake codes.
- If you see placeholder text like "[code]", "[TBD]", "[to be filled]", do NOT extract anything.
- When in doubt, return an empty list. It is better to miss a code than to invent one.

Output JSON ONLY, with the following top-level keys:
- language: ISO language name or code (e.g., "en", "fr").
- translated_text: full document text in English.
- cpv_codes: list of strings. ONLY include codes that are explicitly written in the document. If none found, return empty list [].
- other_codes: list of strings with code type and value. ONLY include codes that are explicitly written. Format as "TYPE: VALUE" (e.g., "UNSPSC: 12345678"). If none found, return empty list [].
- key_requirements_summary: markdown bullet list (as a single string).
- metadata: object with any additional fields you consider useful (deadlines, contract value, identifiers, etc.). Only include fields that are explicitly mentioned in the document.

Respond with STRICTLY valid JSON. Do not include explanations.
"""


@functools.lru_cache(maxsize=128)
def _run_extraction_agent_cached(document_text: str) -> ExtractionResult:
    user_prompt = (
        "Here is the raw text of an RFP / tender document:\n\n"
        f"```rfp_text\n{document_text}\n```\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "- Extract ONLY information that is explicitly written in the document above.\n"
        "- Do NOT invent or create codes, numbers, or identifiers that are not present in the text.\n"
        "- Do NOT extract placeholder codes like '12345678' unless they are explicitly written in the document.\n"
        "- If codes are not mentioned or only placeholders are mentioned, return empty lists [].\n"
        "- Only extract codes that you can see written with their code type (e.g., 'CPV 12345678' or 'CPV code: 12345678').\n"
        "- When in doubt, return an empty list. It is better to miss a code than to invent one.\n"
        "- Only extract what you can see written in the document."
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
            "metadata": {},
        }


    def _filter_suspicious_codes(codes: list) -> list:
        """Filter out codes that look like placeholders or generic numbers."""
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
    other_codes = _filter_suspicious_codes(data.get("other_codes", []) or [])
    
    result = ExtractionResult(
        translated_text="",
        language=data.get("language", "en"),
        cpv_codes=cpv_codes,
        other_codes=other_codes,
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


