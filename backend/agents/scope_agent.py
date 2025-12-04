from __future__ import annotations

import functools
import logging
from dataclasses import dataclass, asdict
from typing import Any, Dict

from backend.llm.client import chat_completion


logger = logging.getLogger(__name__)
SCOPE_MODEL = "meta-llama/Llama-3.1-8B-Instruct"


@dataclass
class ScopeResult:
    essential_text: str
    removed_text: str
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


SCOPE_SYSTEM_PROMPT = """
You are an expert RFP scoping assistant for a bidding team.

You receive:
1) An English version of the RFP.

Your job:
- Remove information that is NOT required for understanding the scope or responding to the tender.
- Keep only the necessary information, such as:
  - Eligibility and qualification criteria.
  - Evaluation criteria.
  - Submission requirements and deadlines.
  - Technical and functional requirements.
  - Contract scope, volumes, SLAs.
- Consider the following as typically unnecessary for scope understanding:
  - Postal addresses of the contracting authority.
  - Corporate boilerplate about the authority, unless directly relevant.
  - Repeated legal boilerplate, unless it implies mandatory requirements.
  - Detailed instructions about website navigation, helpdesk contact details, etc.

Output JSON ONLY with these three fields:
- essential_text: Plain text string containing the cleaned document text with only necessary information. This must be plain text, NOT JSON. Just the text content itself.
- removed_text: Plain text string containing the passages you removed, or a summary of what was removed. This must be plain text, NOT JSON.
- rationale: Plain text string with a short explanation (bullet style) of your scoping decisions.

CRITICAL: essential_text and removed_text must be plain text strings, not JSON objects or structures. They should contain the actual text content, not nested JSON.

Example format:
{
  "essential_text": "The Ministry invites proposals for...",
  "removed_text": "Address: 123 Main St...",
  "rationale": "- Removed address as it's not needed for response"
}

Respond with STRICTLY valid JSON. Do not include explanations.
"""

SCOPE_SYSTEM_PROMPT_ALT1 = """
You are an RFP text filter. Your task is to remove unnecessary content from an RFP document.

Keep ONLY information needed to:
- Understand what the buyer wants (requirements, criteria, scope)
- Know how to respond (submission format, deadlines, evaluation)

Remove:
- Physical addresses
- Generic corporate information
- Redundant legal text
- Navigation instructions

Return JSON with three fields (all must be plain text strings, NOT JSON):
- essential_text: Plain text string with the cleaned, essential content
- removed_text: Plain text string with what you removed
- rationale: Plain text string explaining why you removed it

IMPORTANT: essential_text and removed_text must be plain text strings, not JSON objects.

Output ONLY valid JSON, no other text.
"""

SCOPE_SYSTEM_PROMPT_ALT2 = """
Extract essential information from this RFP document. Remove boilerplate, addresses, and non-critical details.

Essential = requirements, criteria, deadlines, scope, submission rules.
Non-essential = addresses, corporate background, navigation help.

JSON format (all values must be plain text strings):
{
  "essential_text": "plain text content here, not JSON",
  "removed_text": "plain text of removed content, not JSON",
  "rationale": "explanation as plain text"
}

CRITICAL: essential_text and removed_text must be plain text strings, NOT JSON objects or nested structures.

Return only valid JSON.
"""


@functools.lru_cache(maxsize=128)
def _run_scope_agent_cached(translated_text: str) -> ScopeResult:
    """
    Internal cached version of scope agent.
    Cache key is based on translated_text.
    """
    import json
    import re

    def _parse_json_safely(raw: str) -> dict:
        """
        Robust JSON parser that handles common LLM output issues:
        - Markdown code fences
        - Trailing commas
        - Control characters
        - Truncated JSON
        - Unescaped quotes in strings
        - Multiple JSON objects
        """
        # Remove markdown fences
        cleaned = (
            raw.replace("```json", "")
            .replace("```", "")
            .strip()
        )
        
        # Remove control characters
        cleaned = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', cleaned)
        
        # Try to find JSON object(s)
        matches = list(re.finditer(r"\{.*?\}", cleaned, flags=re.DOTALL))
        if matches:
            # Use the longest match (most likely to be complete)
            longest_match = max(matches, key=lambda m: m.end() - m.start())
            cleaned = longest_match.group(0)
        
        # Remove trailing commas before closing braces/brackets
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        
        # Try to fix unclosed strings (common in truncated JSON)
        # Count quotes to see if we have an odd number (unclosed string)
        quote_count = cleaned.count('"')
        if quote_count % 2 != 0:
            # Try to close the last string
            last_quote_pos = cleaned.rfind('"')
            if last_quote_pos > 0:
                # Check if it's inside a value (not a key)
                before_quote = cleaned[:last_quote_pos]
                if before_quote.rstrip().endswith(':'):
                    # It's a key, add empty value
                    cleaned = cleaned[:last_quote_pos + 1] + '""'
                else:
                    # It's a value, might be truncated - try to close it
                    cleaned = cleaned[:last_quote_pos + 1] + '"'
        
        # Try to close unclosed objects/arrays
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
            
            # Try partial extraction as fallback
            try:
                partial = {}
                
                # Try to extract essential_text
                essential_match = re.search(
                    r'"essential_text"\s*:\s*"((?:[^"\\]|\\.)*)"',
                    cleaned,
                    flags=re.DOTALL
                )
                if not essential_match:
                    # Try without quotes (might be unquoted)
                    essential_match = re.search(
                        r'"essential_text"\s*:\s*([^,}\]]+)',
                        cleaned,
                        flags=re.DOTALL
                    )
                if essential_match:
                    partial['essential_text'] = essential_match.group(1).strip('"')
                
                # Try to extract removed_text
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
                
                # Try to extract rationale
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

    # Retry logic with different prompts
    prompts_to_try = [
        (SCOPE_SYSTEM_PROMPT, "You are given an English RFP text.\n\n=== RFP TEXT (ENGLISH) ===\n{text}\n\nIMPORTANT: Return JSON where essential_text and removed_text are plain text strings, NOT JSON objects."),
        (SCOPE_SYSTEM_PROMPT_ALT1, "Filter this RFP text. Keep only essential information:\n\n{text}\n\nReturn JSON only. essential_text and removed_text must be plain text strings."),
        (SCOPE_SYSTEM_PROMPT_ALT2, "Process this RFP:\n\n{text}\n\nExtract essential content, remove boilerplate. Return JSON with plain text strings, not nested JSON."),
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

            if data and data.get("essential_text"):
                # Post-process: If essential_text looks like JSON, try to extract plain text
                essential_text = data.get("essential_text", "")
                removed_text = data.get("removed_text", "")
                
                # Check if essential_text is actually a JSON string (common mistake)
                if isinstance(essential_text, str) and essential_text.strip().startswith("{"):
                    try:
                        # Try to parse it as JSON
                        parsed_json = json.loads(essential_text)
                        # If it's a dict, try to extract text values
                        if isinstance(parsed_json, dict):
                            # Look for common text fields
                            text_parts = []
                            for key in ["text", "content", "essential", "body", "description"]:
                                if key in parsed_json and isinstance(parsed_json[key], str):
                                    text_parts.append(parsed_json[key])
                            # Or just concatenate all string values
                            if not text_parts:
                                text_parts = [str(v) for v in parsed_json.values() if isinstance(v, str)]
                            if text_parts:
                                essential_text = "\n\n".join(text_parts)
                                logger.warning(
                                    "Scope agent: extracted plain text from JSON in essential_text field"
                                )
                    except (json.JSONDecodeError, ValueError):
                        # Not valid JSON, might be malformed - keep as is
                        pass
                
                # Same check for removed_text
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
                
                # Success!
                result = ScopeResult(
                    essential_text=essential_text,
                    removed_text=removed_text,
                    rationale=data.get("rationale", ""),
                )
                logger.info(
                    "Scope agent: finished (essential_chars=%d, removed_chars=%d, attempt=%d)",
                    len(result.essential_text or ""),
                    len(result.removed_text or ""),
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

    # All attempts failed
    logger.error(
        "Scope agent: all %d attempts failed, falling back to raw translated text",
        len(prompts_to_try),
    )
    if last_error:
        logger.exception("Last error was:", exc_info=last_error)
    
    result = ScopeResult(
        essential_text=translated_text,
        removed_text="",
        rationale="Scope agent failed after all retry attempts; using full translated text as essential_text.",
    )
    logger.info(
        "Scope agent: finished (essential_chars=%d, removed_chars=%d) - FALLBACK MODE",
        len(result.essential_text or ""),
        len(result.removed_text or ""),
    )
    return result


def run_scope_agent(
    translated_text: str,
) -> ScopeResult:
    """
    Runs the scope agent on translated text.
    Results are cached using LRU cache based on translated text.
    """
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
    
    # Check if this was a cache hit
    new_cache_info = _run_scope_agent_cached.cache_info()
    if new_cache_info.hits > cache_info.hits:
        logger.info("Scope agent: cache HIT - returned cached result")
    else:
        logger.info("Scope agent: cache MISS - processed new request")
    
    return result


