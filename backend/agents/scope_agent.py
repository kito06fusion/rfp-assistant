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


SCOPE_SYSTEM_PROMPT = """Extract necessary RFP text (80-95% of original).

Keep: requirements, scope, objectives, evaluation criteria, structure requirements.
Remove: emails, addresses, phone numbers, contact names, signatures, metadata, headers/footers, legal boilerplate, placeholder dates like [DD Month YYYY].

IMPORTANT EXCEPTION:
- DO NOT remove any clauses describing the rights or remedies of the Ministry/Buyer/Authority (e.g. "Rights of the Ministry", "Rights of the Buyer", termination rights, penalties, audit rights, inspection rights). These are part of the commercial terms and MUST be kept in the necessary_text.

CRITICAL: The removed_text field MUST contain the ACTUAL removed text content (not just a description). List each removed section verbatim, separated by '---REMOVED SECTION---'.

Output JSON: necessary_text (complete text with removed parts excluded), removed_text (actual removed content, verbatim), rationale (brief explanation)."""

COMPARISON_SYSTEM_PROMPT = """You are a quality assurance agent comparing the original RFP text with the extracted/cleaned text.

Your task is to:
1. Verify that ONLY administrative items were removed (emails, addresses, phone numbers, contact names, signatures, metadata, headers/footers, legal boilerplate)
2. Check that NO substantive content is missing (requirements, scope, objectives, evaluation criteria, technical specifications, proposal structure requirements)
3. Identify any substantive content that appears in the original but is missing from the extracted text
4. Verify that the removed_text contains only administrative items, not requirements or other substantive content

Be thorough and specific. If you find missing substantive content, list it clearly. If everything looks good, explain what you verified.

Output JSON with:
- agreement (bool): true if only admin items removed and no substantive content missing, false otherwise
- missing_items (list of strings): List of specific substantive content items that are in the original but missing from extracted text. Each item should be a clear description (e.g., "Requirement for 99.9% uptime SLA", "Evaluation criterion: technical approach (40 points)", "Section 3.2: Data retention requirements"). Empty list [] if nothing missing.
- removed_items_analysis (list of strings, optional): List of substantive items found in removed_text that should NOT have been removed. Only include items that are clearly substantive (requirements, scope, objectives, etc.). Empty list [] if removed_text only contains admin items.
- notes (string): Detailed explanation of your findings. Describe what you checked, what you found, and any concerns. Be specific - mention what types of content you verified (requirements, scope, objectives, etc.) and whether they are all present in the extracted text."""

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
    text_input = translated_text[:30000] if len(translated_text) > 30000 else translated_text
    user_prompt = f"""RFP text:
{text_input}

Extract necessary text (80-95% of original). 

REMOVE and list in removed_text:
- Email addresses (e.g., procurement@example.com)
- Physical addresses
- Phone numbers
- Contact person names and titles
- Signature blocks
- Placeholder dates like [DD Month YYYY]
- Page headers/footers
- Copyright notices
- Legal boilerplate sections
- Document metadata

IMPORTANT: Do NOT remove or exclude any clauses describing the rights or remedies of the Ministry, Buyer, Contracting Authority, or similar entities. These rights clauses are important commercial terms and MUST remain in necessary_text, not in removed_text.

KEEP in necessary_text:
- All requirements, scope, objectives, evaluation criteria
- Proposal structure requirements
- Technical and functional requirements

IMPORTANT: removed_text must contain the ACTUAL removed text verbatim, not just a description. Separate multiple removed sections with '---REMOVED SECTION---'."""

    system_tokens = len(SCOPE_SYSTEM_PROMPT) // 4
    user_tokens = len(user_prompt) // 4
    total_input_tokens = system_tokens + user_tokens + 100
    logger.info("Scope prompt tokens: system=%d, user=%d, total=%d", system_tokens, user_tokens, total_input_tokens)
    estimated_output_chars = len(translated_text) * 0.95 * 1.5
    estimated_output_tokens = int(estimated_output_chars // 4) + 1000
    max_output_tokens = max(3000, min(6000, min(estimated_output_tokens, 32769 - total_input_tokens - 1000)))
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
            
            # Log removed text for debugging
            if removed_text and len(removed_text.strip()) > 0:
                logger.info("Scope agent: removed_text length=%d chars, preview: %s", len(removed_text), removed_text[:200])
            else:
                logger.warning("Scope agent: removed_text is empty - LLM may not have extracted removed content properly")
            
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
            # Use larger samples for better comparison - include beginning, middle, and end
            # For original text: first 5000, middle 2000, last 3000
            # For extracted text: first 5000, middle 2000, last 3000
            # For removed text: up to 2000 chars
            orig_parts = []
            if len(translated_text) > 10000:
                orig_parts.append(f"[BEGINNING - first 5000 chars]:\n{translated_text[:5000]}")
                mid_start = len(translated_text) // 2 - 1000
                orig_parts.append(f"\n\n[MIDDLE - around position {mid_start}]:\n{translated_text[mid_start:mid_start+2000]}")
                orig_parts.append(f"\n\n[END - last 3000 chars]:\n{translated_text[-3000:]}")
            else:
                orig_parts.append(translated_text)
            original_sample = "\n".join(orig_parts)
            
            nec_parts = []
            if len(necessary_text) > 10000:
                nec_parts.append(f"[BEGINNING - first 5000 chars]:\n{necessary_text[:5000]}")
                mid_start = len(necessary_text) // 2 - 1000
                nec_parts.append(f"\n\n[MIDDLE - around position {mid_start}]:\n{necessary_text[mid_start:mid_start+2000]}")
                nec_parts.append(f"\n\n[END - last 3000 chars]:\n{necessary_text[-3000:]}")
            else:
                nec_parts.append(necessary_text)
            necessary_sample = "\n".join(nec_parts)
            
            rem_sample = removed_text[:2000] if len(removed_text) > 2000 else removed_text
            
            comparison_prompt = f"""ORIGINAL RFP TEXT (total {len(translated_text)} characters):
{original_sample}

EXTRACTED/CLEANED TEXT (total {len(necessary_text)} characters):
{necessary_sample}

REMOVED TEXT (total {len(removed_text)} characters):
{rem_sample if removed_text else "(empty - no text was removed)"}

TASK:
1. Compare the original text with the extracted text. Identify any substantive content (requirements, scope, objectives, evaluation criteria, technical specs, proposal structure requirements) that appears in the ORIGINAL but is MISSING from the EXTRACTED text.

2. Analyze the REMOVED text. Check if it contains only administrative items (emails, addresses, phone numbers, contact names, signatures, metadata, headers/footers, legal boilerplate) OR if it incorrectly contains substantive content (requirements, scope, objectives, etc.).

3. Provide a detailed analysis:
   - List any missing substantive items from the original that should be in extracted
   - List any substantive items found in removed_text that should NOT have been removed
   - Explain what you verified and your overall assessment

Be thorough and specific. If you find problems, list them clearly. If everything is correct, explain what you verified."""

            comp_system_tokens = len(COMPARISON_SYSTEM_PROMPT) // 4
            comp_user_tokens = len(comparison_prompt) // 4
            comp_total = comp_system_tokens + comp_user_tokens + 100
            logger.info("Comparison prompt tokens: system=%d, user=%d, total=%d", comp_system_tokens, comp_user_tokens, comp_total)
            # Increased max tokens to allow for detailed analysis with missing items and notes
            max_output_tokens = max(2000, min(4000, 32769 - comp_total - 1000))
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
                removed_items_analysis = comparison_data.get("removed_items_analysis", [])
                notes = comparison_data.get("notes", "")
                
                # Build detailed comparison notes from actual findings
                note_parts = []
                
                if missing_items:
                    note_parts.append(f"⚠️ MISSING SUBSTANTIVE CONTENT ({len(missing_items)} items):")
                    for i, item in enumerate(missing_items[:10], 1):
                        note_parts.append(f"  {i}. {str(item)[:200]}")
                    if len(missing_items) > 10:
                        note_parts.append(f"  ... and {len(missing_items) - 10} more items")
                
                if removed_items_analysis:
                    # Handle list of strings (substantive items that were incorrectly removed)
                    substantive_removed = []
                    for item in removed_items_analysis:
                        if isinstance(item, str):
                            substantive_removed.append(item)
                        elif isinstance(item, dict):
                            # Handle dict format if LLM uses it
                            item_text = item.get("item", item.get("content", item.get("text", str(item))))
                            if item_text:
                                substantive_removed.append(str(item_text))
                    
                    if substantive_removed:
                        note_parts.append(f"\n⚠️ SUBSTANTIVE CONTENT INCORRECTLY REMOVED ({len(substantive_removed)} items):")
                        for i, item in enumerate(substantive_removed[:10], 1):
                            note_parts.append(f"  {i}. {str(item)[:200]}")
                        if len(substantive_removed) > 10:
                            note_parts.append(f"  ... and {len(substantive_removed) - 10} more items")
                
                if notes:
                    note_parts.append(f"\n📋 ANALYSIS:\n{notes}")
                
                if not note_parts:
                    # No issues found - but still include the LLM's analysis
                    if notes:
                        note_parts.append(f"✅ VALIDATION PASSED:\n{notes}")
                    else:
                        note_parts.append(f"✅ Validation passed. Coverage: {necessary_ratio*100:.1f}%.")
                
                comparison_notes = "\n".join(note_parts)
                
                logger.info(
                    "Scope agent: comparison step completed (agreement=%s, missing_items=%d, coverage=%.1f%%)",
                    comparison_agreement,
                    len(missing_items),
                    necessary_ratio * 100
                )
                if missing_items:
                    logger.warning("Scope agent: comparison found %d missing substantive items", len(missing_items))
            else:
                logger.warning("Scope agent: comparison step returned invalid data")
                comparison_notes = f"⚠️ Comparison validation returned invalid data. Coverage: {necessary_ratio*100:.1f}%. Please review manually."
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
