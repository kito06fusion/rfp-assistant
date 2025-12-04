from __future__ import annotations

import functools
import json
import logging
import re
from typing import Any, Dict

from backend.llm.client import chat_completion
from backend.models import ScopeResult


logger = logging.getLogger(__name__)
SCOPE_MODEL = "meta-llama/Llama-3.1-8B-Instruct"


SCOPE_SYSTEM_PROMPT = """
You are an expert RFP scoping assistant for a bidding team.

You receive an English version of the RFP/tender document.

Your job:
- Identify ONLY very small, specific text snippets that are purely administrative and NOT needed for understanding requirements or responding.

STRICT RULES - ONLY REMOVE THESE EXACT TYPES:
1. Physical postal addresses (e.g., "123 Main Street, City, Country 12345")
2. Email addresses used only for contact (e.g., "procurement@ministry.gov" or "For questions, email: info@ministry.gov")
3. Phone numbers (e.g., "Phone: +1-234-567-8900")
4. Office hours (e.g., "Office hours: Monday-Friday 9am-5pm")
5. Website navigation instructions (e.g., "Click the 'Submit' button on the portal")

ABSOLUTELY DO NOT REMOVE (these are CRITICAL for responding):
- RFP numbers or reference numbers (e.g., "RFP No: MTI/BPM/2024/01")
- ANY deadlines or dates (submission deadlines, question deadlines, award dates, timeline dates, etc.)
- ANY timeline information (RFP issue date, submission deadline, award date, etc.)
- Timeline sections (e.g., "RFP issue date: [DD Month YYYY]", "Proposal submission deadline: [DD Month YYYY, HH:MM]")
- Deadline information (e.g., "Deadline for submission of questions", "Expected award of contract")
- Submission email addresses (if they're for submitting proposals)
- Requirements sections
- Objectives
- Background
- Evaluation criteria
- Legal rights or terms (e.g., "MTI reserves the right to...")
- Contract terms
- Any text that describes what the buyer wants
- Any text that describes how to respond or when to respond
- Headers or titles (unless they're just addresses)
- Dates in any format (e.g., "[DD Month YYYY]", "January 15, 2024", etc.)
- Any line containing "deadline", "date", "timeline", "award", "submission", "question" when referring to dates/deadlines

CRITICAL REQUIREMENTS:
- Only identify VERY SMALL snippets (typically 1-3 sentences max, or single lines like addresses).
- Each removed snippet should be standalone (an address, an email, office hours, etc.).
- Do NOT remove entire paragraphs, sections, or any content about requirements.
- Output ONLY the exact text snippets from the document that should be removed.
- Copy the text EXACTLY as it appears in the document (word-for-word).
- If multiple small snippets should be removed, include all of them separated by clear markers (e.g., "---REMOVED SECTION 1---").
- If no text should be removed, return an empty string.
- The removed_text should typically be less than 3% of the total document length.

Output JSON ONLY with these two fields:
- removed_text: Plain text string containing ONLY very small, specific EXACT text snippets (addresses, contact emails, office hours). Each snippet should be 1-3 sentences or less.
- rationale: Plain text string with a short explanation (bullet style) of why these specific snippets were identified as unnecessary.

Example format (removed_text should be very small snippets like this):
{
  "removed_text": "123 Main Street\nCity, Country 12345\n\n---REMOVED SECTION 2---\n\nFor general inquiries, contact: info@ministry.gov\nOffice hours: Monday-Friday 9am-5pm",
  "rationale": "- Removed postal address (not needed for response)\n- Removed general inquiry contact and office hours (administrative only)"
}

CRITICAL: Do NOT include deadlines, dates, timeline information, or any text containing words like "deadline", "date", "timeline", "award", "submission deadline", "question deadline" in removed_text. These are essential for responding to the RFP. Examples of what NOT to remove: "RFP issue date: [DD Month YYYY]", "Proposal submission deadline: [DD Month YYYY, HH:MM]", "Expected award of contract: [DD Month YYYY]".

Respond with STRICTLY valid JSON. Do not include explanations.
"""

SCOPE_SYSTEM_PROMPT_ALT1 = """
You are an RFP text filter. Your task is to identify ONLY very small administrative snippets.

ONLY identify for removal (VERY SMALL snippets, 1-3 sentences max):
- Physical addresses (e.g., "123 Main St, City, Country")
- General contact emails (e.g., "For inquiries: contact@example.com")
- Office hours
- Website navigation instructions

ABSOLUTELY DO NOT remove (these are CRITICAL):
- RFP numbers or reference numbers
- ANY deadlines, dates, or timeline information (submission deadlines, question deadlines, award dates, RFP issue dates, timeline dates, etc.)
- Timeline sections (e.g., "RFP issue date:", "Proposal submission deadline:", "Expected award of contract:")
- Submission email addresses
- Requirements, objectives, background
- Evaluation criteria
- Legal rights or terms
- Any content about what the buyer wants or how to respond or when to respond
- Any line containing "deadline", "date", "timeline", "award", "submission", "question" when referring to dates/deadlines

CRITICAL: Output ONLY very small, specific EXACT text snippets (1-3 sentences max per snippet). Each snippet should be standalone (an address, an email, etc.). Do NOT remove paragraphs or sections. Removed text should be less than 3% of document.

Return JSON with two fields:
- removed_text: Plain text string with ONLY very small EXACT snippets (addresses, contact emails, office hours). Each snippet 1-3 sentences max.
- rationale: Plain text string explaining why these small snippets are unnecessary

Output ONLY valid JSON, no other text.
"""

SCOPE_SYSTEM_PROMPT_ALT2 = """
Identify ONLY very small administrative text snippets in this RFP document.

ONLY remove (VERY SMALL, 1-3 sentences max):
- Physical addresses
- General contact emails (not submission emails)
- Office hours
- Navigation help

DO NOT remove (these are CRITICAL):
- RFP numbers, reference numbers
- ANY deadlines, dates, or timeline information (submission deadlines, question deadlines, award dates, RFP issue dates, timeline dates, etc.)
- Submission emails
- Requirements, objectives, background
- Evaluation criteria
- Legal rights/terms
- Any content about requirements or how to respond or when to respond
- Dates in any format

CRITICAL: Output ONLY very small EXACT snippets (1-3 sentences max each). Each should be standalone. Removed text should be less than 3% of document.

JSON format:
{
  "removed_text": "very small exact snippets (addresses, contact emails, office hours), separated by markers",
  "rationale": "explanation as plain text"
}

Return only valid JSON.
"""


@functools.lru_cache(maxsize=128)
def _run_scope_agent_cached(translated_text: str) -> ScopeResult:
    def _parse_json_safely(raw: str) -> dict:
        cleaned = (
            raw.replace("```json", "")
            .replace("```", "")
            .strip()
        )
        
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
            error_pos = getattr(e, 'pos', None)
            logger.debug("JSON parse error at position %s: %s", error_pos, str(e))
            
            try:
                partial = {}
                
                removed_match = re.search(
                    r'"removed_text"\s*:\s*"((?:[^"\\]|\\.)*)"',
                    cleaned,
                    flags=re.DOTALL
                )
                if not removed_match:
                    removed_match = re.search(
                        r'"removed_text"\s*:\s*([^,}\]]+)',
                        cleaned,
                        flags=re.DOTALL
                    )
                if removed_match:
                    partial['removed_text'] = removed_match.group(1).strip('"')
                
                rationale_match = re.search(
                    r'"rationale"\s*:\s*"((?:[^"\\]|\\.)*)"',
                    cleaned,
                    flags=re.DOTALL
                )
                if not rationale_match:
                    rationale_match = re.search(
                        r'"rationale"\s*:\s*([^,}\]]+)',
                        cleaned,
                        flags=re.DOTALL
                    )
                if rationale_match:
                    partial['rationale'] = rationale_match.group(1).strip('"')
                
                if partial:
                    logger.warning(
                        "Partially parsed JSON, using extracted fields with defaults"
                    )
                    return partial
            except Exception as parse_exc:
                logger.debug("Partial extraction also failed: %s", parse_exc)
            
            logger.error("Failed to parse JSON after all cleanup attempts")
            logger.debug("Problematic JSON (first 1500 chars):\n%s", cleaned[:1500])
            return {}

    logger.info(
        "Scope agent: processing (translated_chars=%d)",
        len(translated_text),
    )

    def _remove_text_snippets(original_text: str, removed_text: str) -> str:
        """
        Remove exact text snippets from the original text.
        Handles multiple removed sections separated by markers.
        """
        if not removed_text or not removed_text.strip():
            return original_text
        
        cleaned = original_text
        # Split removed_text by common delimiters to get individual snippets
        # First try to split by explicit markers
        sections = re.split(r'---REMOVED SECTION \d+---|---REMOVED---|===REMOVED===|--- Page Break ---', removed_text, flags=re.IGNORECASE)
        
        # Filter out empty sections and normalize
        sections = [s.strip() for s in sections if s.strip()]
        
        # If no markers found, treat the whole removed_text as one snippet
        if len(sections) == 0:
            sections = [removed_text.strip()]
        
        for section in sections:
            section = section.strip()
            if not section or len(section) < 10:  # Skip very short snippets
                continue
            
            # Try exact match first (most reliable)
            if section in cleaned:
                # Find the position to ensure we're removing a complete section
                pos = cleaned.find(section)
                if pos >= 0:
                    # Remove the section, preserving surrounding context
                    before = cleaned[:pos].rstrip()
                    after = cleaned[pos + len(section):].lstrip()
                    # Clean up any orphaned punctuation or fragments
                    # Remove trailing punctuation that might be left behind
                    before = re.sub(r'[.,;:]\s*$', '', before)
                    # Join with a single space if both parts exist
                    if before and after:
                        cleaned = before + ' ' + after
                    elif before:
                        cleaned = before
                    elif after:
                        cleaned = after
                    else:
                        cleaned = ""
                    logger.debug("Removed exact text snippet (%d chars)", len(section))
                    continue
            
            # Try normalized whitespace match (for cases where whitespace differs)
            section_normalized = re.sub(r'\s+', ' ', section.strip())
            cleaned_normalized = re.sub(r'\s+', ' ', cleaned)
            
            if section_normalized in cleaned_normalized:
                # Find position in normalized text
                pos_normalized = cleaned_normalized.find(section_normalized)
                
                # Map back to original text position
                # Count characters up to the match in normalized version
                before_normalized = cleaned_normalized[:pos_normalized]
                # Find corresponding position in original by matching character count
                # (accounting for whitespace differences)
                original_pos = 0
                normalized_idx = 0
                for i, char in enumerate(cleaned):
                    if normalized_idx >= pos_normalized:
                        original_pos = i
                        break
                    # Count this character in normalized version
                    if char.isspace():
                        # Whitespace collapses to single space in normalized
                        if normalized_idx == 0 or cleaned_normalized[normalized_idx - 1] != ' ':
                            normalized_idx += 1
                    else:
                        normalized_idx += 1
                
                # Try to find exact match near the calculated position
                search_start = max(0, original_pos - 50)
                search_end = min(len(cleaned), original_pos + len(section) + 50)
                search_area = cleaned[search_start:search_end]
                
                # Try exact match in search area
                if section in search_area:
                    pos_in_area = search_area.find(section)
                    actual_pos = search_start + pos_in_area
                    before = cleaned[:actual_pos].rstrip()
                    after = cleaned[actual_pos + len(section):].lstrip()
                    before = re.sub(r'[.,;:]\s*$', '', before)
                    if before and after:
                        cleaned = before + ' ' + after
                    elif before:
                        cleaned = before
                    elif after:
                        cleaned = after
                    logger.debug("Removed text snippet from search area (%d chars)", len(section))
                    continue
                
                # If exact match not found, try normalized match in search area
                search_area_normalized = re.sub(r'\s+', ' ', search_area)
                if section_normalized in search_area_normalized:
                    pos_in_area = search_area_normalized.find(section_normalized)
                    # Approximate position
                    actual_pos = search_start + pos_in_area
                    # Try to find boundaries by looking for word boundaries
                    end_pos = actual_pos + len(section_normalized)
                    # Find actual end by matching word boundaries
                    before = cleaned[:actual_pos].rstrip()
                    after = cleaned[end_pos:].lstrip()
                    before = re.sub(r'[.,;:]\s*$', '', before)
                    if before and after:
                        cleaned = before + ' ' + after
                    elif before:
                        cleaned = before
                    elif after:
                        cleaned = after
                    logger.debug("Removed approximate text snippet (%d chars)", len(section))
                    continue
        
        # Clean up extra whitespace and orphaned punctuation
        cleaned = re.sub(r'\n\n\n+', '\n\n', cleaned)
        cleaned = re.sub(r'[ \t]+', ' ', cleaned)  # Normalize spaces
        # Remove orphaned punctuation at line starts
        cleaned = re.sub(r'\n\s*[.,;:]\s*', '\n', cleaned)
        return cleaned.strip()

    prompts_to_try = [
        (SCOPE_SYSTEM_PROMPT, "You are given an English RFP text.\n\n=== RFP TEXT (ENGLISH) ===\n{text}\n\nCRITICAL: Identify ONLY small, specific text snippets to remove (addresses, contact info, office hours, etc.). DO NOT remove deadlines, dates, timeline information, or submission deadlines - these are essential for responding. Do NOT identify large sections or main content. The removed text should be less than 3% of the document. Output ONLY the exact small snippets, word-for-word."),
        (SCOPE_SYSTEM_PROMPT_ALT1, "Identify ONLY small unnecessary snippets in this RFP:\n\n{text}\n\nOnly identify small snippets like addresses, contact info, office hours. DO NOT remove deadlines, dates, or timeline information. Do NOT identify requirements, objectives, or main content. Return JSON."),
        (SCOPE_SYSTEM_PROMPT_ALT2, "Process this RFP:\n\n{text}\n\nIdentify ONLY small text snippets (addresses, contact info) that should be removed. DO NOT remove deadlines, dates, or timeline information. Do NOT identify main content. Return JSON."),
    ]

    last_error = None
    for attempt, (system_prompt, user_template) in enumerate(prompts_to_try, 1):
        try:
            user_prompt = user_template.format(text=translated_text)
            
            logger.debug("Scope agent: attempt %d/%d", attempt, len(prompts_to_try))
            
            content = chat_completion(
                model=SCOPE_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=None,
            )

            data = _parse_json_safely(content)

            if data and data.get("removed_text") is not None:
                removed_text = data.get("removed_text", "")
                
                # Handle case where removed_text might be JSON string
                if isinstance(removed_text, str) and removed_text.strip().startswith("{"):
                    try:
                        parsed_json = json.loads(removed_text)
                        if isinstance(parsed_json, dict):
                            text_parts = [str(v) for v in parsed_json.values() if isinstance(v, str)]
                            if text_parts:
                                removed_text = "\n\n".join(text_parts)
                                logger.warning(
                                    "Scope agent: extracted plain text from JSON in removed_text field"
                                )
                    except (json.JSONDecodeError, ValueError):
                        pass
                
                # Validate: removed_text should be a very small portion of the document (max 5%)
                # If it's too large, the agent likely misunderstood and identified main content
                removed_ratio = len(removed_text) / len(translated_text) if translated_text else 0
                if removed_ratio > 0.05:  # More than 5% of document
                    logger.warning(
                        "Scope agent: removed_text is too large (%.1f%% of document). "
                        "Likely identified main content instead of small snippets. Rejecting this result.",
                        removed_ratio * 100
                    )
                    # Try next prompt instead
                    continue
                
                # Safety check: Filter out any deadline/timeline-related content from removed_text
                deadline_keywords = [
                    "deadline", "date:", "timeline", "award of contract", "submission deadline",
                    "question deadline", "issue date", "expected award", "rfp issue", "proposal submission"
                ]
                removed_lower = removed_text.lower()
                if any(keyword in removed_lower for keyword in deadline_keywords):
                    logger.warning(
                        "Scope agent: removed_text contains deadline/timeline information. "
                        "This should not be removed. Filtering it out."
                    )
                    # Split by markers and filter out deadline-related sections
                    sections = re.split(r'---REMOVED SECTION \d+---|---REMOVED---|===REMOVED===|--- Page Break ---', removed_text, flags=re.IGNORECASE)
                    filtered_sections = []
                    for section in sections:
                        section = section.strip()
                        if not section:
                            continue
                        section_lower = section.lower()
                        # Keep only if it doesn't contain deadline keywords
                        if not any(keyword in section_lower for keyword in deadline_keywords):
                            filtered_sections.append(section)
                    
                    if filtered_sections:
                        removed_text = "\n\n---REMOVED SECTION---\n\n".join(filtered_sections)
                    else:
                        # All sections contained deadlines, so nothing should be removed
                        removed_text = ""
                        logger.info("Scope agent: All removed sections contained deadlines. Setting removed_text to empty.")
                
                # Remove the identified text snippets from the original text
                cleaned_text = _remove_text_snippets(translated_text, removed_text)
                
                result = ScopeResult(
                    removed_text=removed_text,
                    rationale=data.get("rationale", ""),
                    cleaned_text=cleaned_text,
                )
                logger.info(
                    "Scope agent: finished (removed_chars=%d, cleaned_chars=%d, attempt=%d)",
                    len(result.removed_text or ""),
                    len(result.cleaned_text or ""),
                    attempt,
                )
                return result
            else:
                # Check if removed_text exists (even if empty, that's valid - means nothing to remove)
                if data and "removed_text" in data:
                    removed_text = data.get("removed_text", "")
                    
                    # Validate: removed_text should be a very small portion (max 5%)
                    removed_ratio = len(removed_text) / len(translated_text) if translated_text else 0
                    if removed_ratio > 0.05:
                        logger.warning(
                            "Scope agent: attempt %d removed_text is too large (%.1f%%). Trying next prompt.",
                            attempt,
                            removed_ratio * 100
                        )
                        continue
                    
                    cleaned_text = _remove_text_snippets(translated_text, removed_text)
                    result = ScopeResult(
                        removed_text=removed_text,
                        rationale=data.get("rationale", ""),
                        cleaned_text=cleaned_text,
                    )
                    logger.info(
                        "Scope agent: finished (removed_chars=%d, cleaned_chars=%d, attempt=%d)",
                        len(result.removed_text or ""),
                        len(result.cleaned_text or ""),
                        attempt,
                    )
                    return result
                else:
                    logger.warning(
                        "Scope agent: attempt %d returned empty or invalid data, trying next prompt",
                        attempt,
                    )
        except Exception as e:
            logger.warning(
                "Scope agent: attempt %d failed with error: %s",
                attempt,
                str(e),
            )
            last_error = e
            continue

    logger.error(
        "Scope agent: all %d attempts failed, falling back to no removal",
        len(prompts_to_try),
    )
    if last_error:
        logger.exception("Last error was:", exc_info=last_error)
    
    # Fallback: no text removed, cleaned_text is same as original
    result = ScopeResult(
        removed_text="",
        rationale="Scope agent failed after all retry attempts; no text removed.",
        cleaned_text=translated_text,
    )
    logger.info(
        "Scope agent: finished (removed_chars=%d, cleaned_chars=%d) - FALLBACK MODE",
        len(result.removed_text or ""),
        len(result.cleaned_text or ""),
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


