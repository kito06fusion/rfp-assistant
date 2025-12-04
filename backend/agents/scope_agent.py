from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Any, Dict

from backend.llm.client import chat_completion


logger = logging.getLogger(__name__)
SCOPE_MODEL = "google/gemma-2-2b-it"


@dataclass
class ScopeResult:
    essential_text: str
    removed_text: str
    rationale: str
    merged_structured_info: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


SCOPE_SYSTEM_PROMPT = """
You are an expert RFP scoping assistant for a bidding team.

You receive:
1) An English version of the RFP (possibly translated).
2) Structured extracted information (CPV codes, deadlines, identifiers, etc.).

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

Output JSON ONLY with:
- essential_text: a cleaned and concise version of the document text containing only necessary information.
- removed_text: the concatenation of passages you removed, or a summary of what was removed.
- rationale: short explanation (bullet style) of your scoping decisions.
- merged_structured_info: object that merges the structured info from the previous agent with any additional fields you identify.

Respond with STRICTLY valid JSON. Do not include explanations.
"""


def run_scope_agent(
    translated_text: str,
    structured_info: Dict[str, Any],
) -> ScopeResult:
    """
    Runs the scope agent to strip non-essential information.
    """
    user_prompt = (
        "You are given an English RFP text and structured metadata from a previous agent.\n\n"
        "=== RFP TEXT (ENGLISH) ===\n"
        f"{translated_text}\n\n"
        "=== STRUCTURED INFO (JSON) ===\n"
        f"{structured_info}"
    )

    logger.info(
        "Scope agent: starting (translated_chars=%d, has_structured=%s)",
        len(translated_text),
        bool(structured_info),
    )

    content = chat_completion(
        model=SCOPE_MODEL,
        messages=[
            {"role": "system", "content": SCOPE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.15,
        max_tokens=None,
    )

    import json
    import re

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
            logger.error("Scope agent: failed to parse JSON: %s", str(e))
            logger.debug("Problematic JSON (first 1000 chars): %s", cleaned[:1000])
            # Return an empty dict so caller can fall back gracefully
            return {}

    data = _parse_json_safely(content)

    # If parsing failed (empty dict), fall back to using the translated text as-is
    if not data:
        logger.warning(
            "Scope agent: falling back to raw translated text because JSON parsing failed."
        )
        result = ScopeResult(
            essential_text=translated_text,
            removed_text="",
            rationale="Scope agent JSON parsing failed; using full translated text as essential_text.",
            merged_structured_info=structured_info or {},
        )
    else:
        result = ScopeResult(
            essential_text=data.get("essential_text", ""),
            removed_text=data.get("removed_text", ""),
            rationale=data.get("rationale", ""),
            merged_structured_info=data.get("merged_structured_info", {}) or {},
        )
    logger.info(
        "Scope agent: finished (essential_chars=%d, removed_chars=%d)",
        len(result.essential_text or ""),
        len(result.removed_text or ""),
    )
    return result


