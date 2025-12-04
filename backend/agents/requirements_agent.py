from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Any, Dict, List

from backend.llm.client import chat_completion


logger = logging.getLogger(__name__)
REQUIREMENTS_MODEL = "meta-llama/Llama-3.1-8B-Instruct"


@dataclass
class RequirementsResult:
    solution_requirements: List[Dict[str, Any]]
    response_structure_requirements: List[Dict[str, Any]]
    notes: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


REQUIREMENTS_SYSTEM_PROMPT = """
You are an RFP requirements analyst.

You receive a scoped RFP text that already contains only necessary information and a set of structured metadata.

Your task is to SPLIT the information into two categories:

1) solution_requirements:
   - These describe what the buyer wants from the solution or service.
   - Examples: functional requirements, technical stack constraints, performance/SLA targets, security/compliance needs, support model, implementation approach, training, reporting, integrations, etc.

2) response_structure_requirements:
   - These describe HOW the bidder must respond.
   - Examples: languages, page/word limits, document structure and headings, mandatory sections, templates to use, format (PDF, DOCX, portal fields), submission method, number of copies, required signed forms, etc.

For each requirement, produce a small object with:
  - id: short machine-friendly identifier (e.g., "SOL-ARCH-01").
  - type: "mandatory" or "optional" where clear from context (otherwise "unspecified").
  - source_text: exact or near-exact snippet from the RFP.
  - normalized_text: concise, unambiguous restatement in clear English suitable for checklists.
  - category: a short tag (e.g., "Architecture", "Security", "SLA", "Submission-Format", "Language", "Evaluation").

Output JSON ONLY with:
- solution_requirements: list of requirement objects.
- response_structure_requirements: list of requirement objects.
- notes: any clarifying comments or assumptions you made.

Respond with STRICTLY valid JSON. Do not include explanations.
"""


def run_requirements_agent(
    essential_text: str,
    structured_info: Dict[str, Any],
) -> RequirementsResult:
    user_prompt = (
        "You are given the scoped RFP text (with unnecessary content removed) and merged structured info.\n\n"
        "=== SCOPED RFP TEXT ===\n"
        f"{essential_text}\n\n"
        "=== STRUCTURED INFO (JSON) ===\n"
        f"{structured_info}"
    )

    logger.info(
        "Requirements agent: starting (essential_chars=%d, has_structured=%s)",
        len(essential_text),
        bool(structured_info),
    )

    content = chat_completion(
        model=REQUIREMENTS_MODEL,
        messages=[
            {"role": "system", "content": REQUIREMENTS_SYSTEM_PROMPT},
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
            logger.error("Requirements agent: failed to parse JSON: %s", str(e))
            logger.debug("Problematic JSON (first 1000 chars): %s", cleaned[:1000])
            raise ValueError(f"LLM requirements agent returned invalid JSON: {str(e)}") from e

    try:
        data = _parse_json_safely(content)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Requirements agent: JSON parsing failed: %s", e)
        raise

    result = RequirementsResult(
        solution_requirements=data.get("solution_requirements", []) or [],
        response_structure_requirements=data.get("response_structure_requirements", []) or [],
        notes=data.get("notes", ""),
    )
    logger.info(
        "Requirements agent: finished (solution=%d, response_structure=%d)",
        len(result.solution_requirements),
        len(result.response_structure_requirements),
    )
    return result


