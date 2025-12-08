from __future__ import annotations

import functools
import json
import logging
import re
from typing import Any, Dict

from backend.llm.client import chat_completion
from backend.models import ScopeResult


logger = logging.getLogger(__name__)
SCOPE_MODEL = "gpt-5-chat"
COMPARISON_MODEL = "gpt-5-chat"


SCOPE_SYSTEM_PROMPT = """
You are an RFP analysis assistant. Your task is to extract the text that is NECESSARY to create a response to this RFP.

KEEP in necessary_text:
- RFP number/identifier and title
- Introduction, Background, Objectives (all substantive content)
- Scope of Work (all of it)
- Requirements (functional, technical, non-functional) - ALL requirements
- Evaluation criteria (the actual criteria)
- Vendor qualifications
- Proposal structure requirements (what sections to include)
- RFP timeline/dates
- How/where to submit questions
- File format instructions

REMOVE from necessary_text (put in removed_text, small administrative snippets):
- Procurement email addresses
- Physical addresses
- Phone numbers
- Named contact people + titles
- Signature blocks
- Document control metadata
- Page headers/footers
- Copyright notices
- Confidentiality legends
- "Rights of the Ministry/Buyer" boilerplate sections
- General legal disclaimers
- Q&A process instructions
- Shortlisting/presentation logistics
- Evaluation admin mechanics
- Page break markers
- Table of contents
- Redundant fluff paragraphs

Output JSON:
{
  "necessary_text": "the COMPLETE RFP text with only small administrative snippets removed (80-95% of original)",
  "removed_text": "ONLY the small administrative snippets that were removed, separated by '---REMOVED SECTION---'",
  "rationale": "brief explanation of what was excluded"
}

CRITICAL: Return the COMPLETE necessary_text - do NOT truncate. Return ONLY valid JSON.
"""

COMPARISON_SYSTEM_PROMPT = """
You are a validation assistant. Compare the extracted necessary text with the original RFP text to verify what was actually removed.

Your task:
1. Identify what substantive content from the original is MISSING from the extracted text
2. Verify that only administrative items were removed (emails, addresses, dates, formatting, etc.)
3. Check if any important substantive content was accidentally removed

The extracted text should EXCLUDE: Administrative contact info, formatting/packaging instructions, timeline/dates sections, Q&A process, legal boilerplate.

The extracted text should INCLUDE: RFP number, requirements, objectives, scope, evaluation criteria, vendor qualifications, proposal structure.

Output JSON:
{
  "agreement": true if only administrative items were removed and all substantive content is present, false if substantive content is missing,
  "missing_items": ["list of specific substantive content that exists in original but is missing from extracted text"],
  "notes": "brief explanation of what was actually removed and whether it was appropriate"
}

Return valid JSON only.
"""

@functools.lru_cache(maxsize=128)
def _run_scope_agent_cached(translated_text: str) -> ScopeResult:
    def _parse_json_safely(raw: str) -> dict:
        cleaned = (
            raw.replace("```json", "")
            .replace("```", "")
            .strip()
        )
        def fix_string(match):
            quote_content = match.group(1)
            fixed = quote_content.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
            fixed = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', fixed)
            return f'"{fixed}"'
        cleaned = re.sub(r'"((?:[^"\\]|\\.)*)"', fix_string, cleaned)
        cleaned = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', cleaned)
        matches = list(re.finditer(r"\{.*?\}", cleaned, flags=re.DOTALL))
        if matches:
            longest_match = max(matches, key=lambda m: m.end() - m.start())
            cleaned = longest_match.group(0)
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        quote_count = cleaned.count('"')
        if quote_count % 2 != 0:
            last_quote_pos = cleaned.rfind('"')
            if last_quote_pos > 0:
                before_quote = cleaned[:last_quote_pos]
                if before_quote.rstrip().endswith(':'):
                    cleaned = cleaned[:last_quote_pos + 1] + '""'
                else:
                    cleaned = cleaned[:last_quote_pos + 1] + '"'
        open_braces = cleaned.count('{')
        close_braces = cleaned.count('}')
        if open_braces > close_braces:
            cleaned += '}' * (open_braces - close_braces)
        open_brackets = cleaned.count('[')
        close_brackets = cleaned.count(']')
        if open_brackets > close_brackets:
            cleaned += ']' * (open_brackets - close_brackets)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON: %s", str(e))
            logger.debug("Problematic JSON (first 1500 chars):\n%s", cleaned[:1500])
            return {}
    logger.info(
        "Scope agent: processing (translated_chars=%d)",
        len(translated_text),
    )
    user_prompt = f"""Process this RFP text. KEEP 80-95% of it in necessary_text (all requirements, objectives, scope, etc.). REMOVE only 5-20% in removed_text (small administrative snippets like emails, addresses, etc.).

RFP text:

{translated_text}

CRITICAL: Return the COMPLETE necessary_text - do NOT truncate. necessary_text should be MOST of the document."""

    estimated_input_tokens = len(user_prompt) // 4 + len(SCOPE_SYSTEM_PROMPT) // 4 + 500
    estimated_output_chars = len(translated_text) * 0.95 * 1.5
    estimated_output_tokens = int(estimated_output_chars // 4) + 1000
    max_output_tokens = max(3000, min(6000, min(estimated_output_tokens, 32769 - estimated_input_tokens - 1000)))
    try:
        content = chat_completion(
            model=SCOPE_MODEL,
            messages=[
                {"role": "system", "content": SCOPE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=max_output_tokens,
        )
        logger.debug("Scope agent: LLM response length=%d chars, first 500 chars: %s", len(content), content[:500])
        data = _parse_json_safely(content)
        if not data:
            logger.error("Scope agent: JSON parsing returned empty dict. Raw response (first 2000 chars): %s", content[:2000])
            necessary_match = re.search(r'"necessary_text"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', content, re.DOTALL)
            removed_match = re.search(r'"removed_text"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', content, re.DOTALL)
            rationale_match = re.search(r'"rationale"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', content, re.DOTALL)
            
            if necessary_match:
                necessary_text = necessary_match.group(1).replace('\\n', '\n').replace('\\"', '"')
                removed_text = removed_match.group(1).replace('\\n', '\n').replace('\\"', '"') if removed_match else ""
                rationale = rationale_match.group(1).replace('\\n', '\n').replace('\\"', '"') if rationale_match else "Extracted from malformed JSON using regex fallback."
                logger.info("Scope agent: extracted text from malformed JSON using regex fallback")
            else:
                logger.warning("Scope agent: no valid necessary_text extracted, using original text")
                necessary_text = translated_text
                removed_text = ""
                rationale = "Scope agent failed to extract necessary text; using original text."
        else:
            necessary_text = data.get("necessary_text", "")
            removed_text = data.get("removed_text", "")
            rationale = data.get("rationale", "")
            if isinstance(necessary_text, list):
                necessary_text = "\n\n".join(str(item) for item in necessary_text if item)
            elif not isinstance(necessary_text, str):
                necessary_text = str(necessary_text) if necessary_text else ""
            if isinstance(removed_text, list):
                removed_text = "\n\n---REMOVED SECTION---\n\n".join(str(item) for item in removed_text if item)
            elif not isinstance(removed_text, str):
                removed_text = str(removed_text) if removed_text else ""
            if not necessary_text or len(necessary_text.strip()) < 100:
                logger.warning("Scope agent: necessary_text too short (%d chars), using original text", len(necessary_text) if necessary_text else 0)
                necessary_text = translated_text
                removed_text = ""
                rationale = "Scope agent failed to extract necessary text; using original text."
        
    except Exception as e:
        logger.error("Scope agent: failed with error: %s", str(e))
        logger.exception("Scope agent error")
        necessary_text = translated_text
        removed_text = ""
        rationale = f"Scope agent failed: {str(e)}"
    logger.info("Scope agent: running comparison validation step")
    comparison_agreement = True
    comparison_notes = ""
    necessary_ratio = len(necessary_text) / len(translated_text) if translated_text else 0
    if necessary_ratio >= 0.95 or (necessary_text == translated_text):
        logger.info("Scope agent: using full text, skipping comparison")
        comparison_agreement = True
        comparison_notes = f"Using full original text ({necessary_ratio*100:.1f}% coverage)."
    else:
        try:
            original_sample = translated_text[:3000]
            if len(translated_text) > 3000:
                original_sample += "\n\n[... middle section omitted ...]\n\n" + translated_text[-1000:]
            necessary_sample = necessary_text[:3000]
            if len(necessary_text) > 3000:
                necessary_sample += "\n\n[... middle section omitted ...]\n\n" + necessary_text[-1000:]
            comparison_prompt = f"""Compare the extracted necessary text with the original RFP text.
Original RFP text (sample, {len(translated_text)} total chars):
{original_sample}
Extracted necessary text (sample, {len(necessary_text)} total chars, {necessary_ratio*100:.1f}% of original):
{necessary_sample}
Removed text (what was excluded, {len(removed_text)} chars):
{removed_text[:1000]}{'...' if len(removed_text) > 1000 else ''}
Your task:
1. Check if any substantive content from the original is missing from the extracted text
2. Verify that the removed_text only contains administrative items (emails, addresses, dates, formatting, etc.)
3. Identify if any important requirements, objectives, scope, or evaluation criteria were accidentally removed"""

            estimated_input_tokens = len(comparison_prompt) // 4 + len(COMPARISON_SYSTEM_PROMPT) // 4 + 500
            max_output_tokens = max(1000, min(2000, 32769 - estimated_input_tokens - 1000))  # Very low limit for comparison (just needs JSON)
            comparison_content = chat_completion(
                model=COMPARISON_MODEL,
                messages=[
                    {"role": "system", "content": COMPARISON_SYSTEM_PROMPT},
                    {"role": "user", "content": comparison_prompt},
                ],
                temperature=0.0,
                max_tokens=max_output_tokens,
            )
            comparison_data = _parse_json_safely(comparison_content)
            if comparison_data:
                comparison_agreement = comparison_data.get("agreement", True)
                if isinstance(comparison_agreement, str):
                    comparison_agreement = comparison_agreement.lower() in ('true', 'yes', '1')
                missing_items = comparison_data.get("missing_items", [])
                notes = comparison_data.get("notes", "")
                if missing_items:
                    comparison_notes = f"Missing items: {', '.join(str(item) for item in missing_items[:5])}"
                    if len(missing_items) > 5:
                        comparison_notes += f" (and {len(missing_items) - 5} more)"
                    if notes:
                        comparison_notes += f". {notes}"
                elif notes:
                    comparison_notes = notes
                else:
                    comparison_notes = f"Validation passed. Coverage: {necessary_ratio*100:.1f}%."
                logger.info(
                    "Scope agent: comparison step completed (agreement=%s, coverage=%.1f%%)",
                    comparison_agreement,
                    necessary_ratio * 100
                )
            else:
                logger.warning("Scope agent: comparison step returned invalid data")
                comparison_notes = f"Comparison validation returned invalid data. Coverage: {necessary_ratio*100:.1f}%."
        except Exception as e:
            logger.warning("Scope agent: comparison step failed (non-critical): %s", str(e))
            comparison_agreement = True
            comparison_notes = f"Comparison step skipped due to timeout/error (non-critical). Coverage: {necessary_ratio*100:.1f}%."
    result = ScopeResult(
        necessary_text=necessary_text,
        removed_text=removed_text,
        rationale=rationale,
        cleaned_text=necessary_text,
        comparison_agreement=comparison_agreement,
        comparison_notes=comparison_notes,
    )
    logger.info(
        "Scope agent: finished (necessary_chars=%d, removed_chars=%d, cleaned_chars=%d, comparison_agreement=%s)",
        len(result.necessary_text or ""),
        len(result.removed_text or ""),
        len(result.cleaned_text or ""),
        result.comparison_agreement,
    )
    return result

def run_scope_agent(
    translated_text: str,
) -> ScopeResult:
    cache_info = _run_scope_agent_cached.cache_info()
    logger.info(
        "Scope agent: starting (translated_chars=%d, cache_hits=%d, cache_misses=%d, cache_size=%d/%d)",
        len(translated_text),
        cache_info.hits,
        cache_info.misses,
        cache_info.currsize,
        cache_info.maxsize,
    )
    result = _run_scope_agent_cached(translated_text)
    new_cache_info = _run_scope_agent_cached.cache_info()
    if new_cache_info.hits > cache_info.hits:
        logger.info("Scope agent: cache HIT - returned cached result")
    else:
        logger.info("Scope agent: cache MISS - processed new request")
    return result
