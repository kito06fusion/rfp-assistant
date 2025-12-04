from __future__ import annotations

import functools
import json
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

CRITICAL: These requirements will be used to create an RFP response. You MUST preserve the COMPLETE original text from the RFP document for each requirement.

For each requirement, produce an object with:
  - id: short machine-friendly identifier (e.g., "SOL-ARCH-01", "RESP-FORMAT-01").
  - type: "mandatory" or "optional" where clear from context (otherwise "unspecified").
  - source_text: THE COMPLETE, FULL original text from the RFP document for this requirement. This must include ALL details, specifications, conditions, and context. Do NOT summarize or truncate. Copy the entire relevant passage verbatim from the original document.
  - normalized_text: a concise, unambiguous restatement in clear English suitable for quick reference/checklists (this can be a summary, but source_text must be complete).
  - category: a short tag (e.g., "Architecture", "Security", "SLA", "Submission-Format", "Language", "Evaluation").

IMPORTANT RULES:
- source_text must contain the COMPLETE original text - include full paragraphs, all specifications, all conditions, all details
- If a requirement spans multiple paragraphs, include ALL of them in source_text
- Do NOT summarize source_text - it must be the verbatim original text
- Break down complex requirements into separate requirement objects if they cover distinct topics, but ensure each source_text is complete for that topic
- normalized_text can be a summary for quick reference, but source_text is the authoritative source

Output JSON ONLY with:
- solution_requirements: list of requirement objects.
- response_structure_requirements: list of requirement objects.
- notes: any clarifying comments or assumptions you made.

Respond with STRICTLY valid JSON. Do not include explanations.
"""


@functools.lru_cache(maxsize=128)
def _run_requirements_agent_cached(essential_text: str, structured_info_json: str) -> RequirementsResult:
    """
    Internal cached version of requirements agent.
    Cache key is based on essential_text and structured_info (as JSON string).
    """
    # Parse structured_info back from JSON
    structured_info = json.loads(structured_info_json) if structured_info_json else {}
    
    user_prompt = (
        "You are given the scoped RFP text (with unnecessary content removed) and merged structured info.\n\n"
        "=== SCOPED RFP TEXT ===\n"
        f"{essential_text}\n\n"
        "=== STRUCTURED INFO (JSON) ===\n"
        f"{structured_info}\n\n"
        "IMPORTANT: For each requirement you extract, the 'source_text' field must contain the COMPLETE, FULL original text from the RFP above. "
        "Do NOT summarize or truncate - include all paragraphs, specifications, conditions, and details verbatim. "
        "This text will be used to create the RFP response, so it must be complete and accurate."
    )

    logger.info(
        "Requirements agent: processing (essential_chars=%d, has_structured=%s)",
        len(essential_text),
        bool(structured_info),
    )

    content = chat_completion(
        model=REQUIREMENTS_MODEL,
        messages=[
            {"role": "system", "content": REQUIREMENTS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=None,
    )

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


def run_requirements_agent(
    essential_text: str,
    structured_info: Dict[str, Any],
) -> RequirementsResult:
    """
    Runs the requirements agent on scoped text and structured info.
    Results are cached using LRU cache based on essential_text and structured_info.
    """
    # Convert structured_info to JSON string for caching (dicts aren't hashable)
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
    
    # Check if this was a cache hit
    new_cache_info = _run_requirements_agent_cached.cache_info()
    if new_cache_info.hits > cache_info.hits:
        logger.info("Requirements agent: cache HIT - returned cached result")
    else:
        logger.info("Requirements agent: cache MISS - processed new request")
    
    return result


