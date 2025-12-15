from __future__ import annotations
import logging
from typing import Dict, Any

from backend.models import (
    ExtractionResult,
    RequirementsResult,
    BuildQuery,
    RequirementItem,
)

logger = logging.getLogger(__name__)


def build_query_for_single_requirement(
    extraction_result: ExtractionResult,
    single_requirement: RequirementItem,
    all_response_structure_requirements: list[RequirementItem],
) -> BuildQuery:
    logger.info("Building query for single requirement: %s", single_requirement.id)

    solution_summary = single_requirement.normalized_text

    response_parts = []
    for req in all_response_structure_requirements:
        response_parts.append(req.normalized_text)

    response_structure_summary = "\n\n".join(response_parts) if response_parts else "No response structure requirements found."

    extraction_data = {
        "language": extraction_result.language,
        "cpv_codes": extraction_result.cpv_codes,
        "other_codes": extraction_result.other_codes,
        "key_requirements_summary": extraction_result.key_requirements_summary,
    }

    query_parts = [
        "RFP RESPONSE GENERATION QUERY",
        "=" * 80,
        "",
        "SOLUTION REQUIREMENT (What the buyer wants):",
        "-" * 80,
        solution_summary,
        "",
        "RESPONSE STRUCTURE REQUIREMENTS (How to respond):",
        "-" * 80,
        response_structure_summary,
        "",
        "EXTRACTION DATA:",
        "-" * 80,
        f"Language: {extraction_result.language}",
        f"CPV Codes: {', '.join(extraction_result.cpv_codes) if extraction_result.cpv_codes else 'None'}",
        f"Other Codes: {', '.join(extraction_result.other_codes) if extraction_result.other_codes else 'None'}",
        "",
        "KEY REQUIREMENTS SUMMARY:",
        extraction_result.key_requirements_summary if extraction_result.key_requirements_summary else "None",
    ]

    query_text = "\n".join(query_parts)

    logger.info(
        "Built query for requirement %s: %d response structure reqs, %d CPV codes, %d other codes",
        single_requirement.id,
        len(all_response_structure_requirements),
        len(extraction_result.cpv_codes),
        len(extraction_result.other_codes),
    )

    return BuildQuery(
        query_text=query_text,
        solution_requirements_summary=solution_summary,
        response_structure_requirements_summary=response_structure_summary,
        extraction_data=extraction_data,
        confirmed=False,
    )


def build_query(
    extraction_result: ExtractionResult,
    requirements_result: RequirementsResult,
) -> BuildQuery:
    logger.info("Building query from extraction and requirements data")

    solution_parts = []
    for req in requirements_result.solution_requirements:
        solution_parts.append(req.normalized_text)

    solution_summary = "\n\n".join(solution_parts) if solution_parts else "No solution requirements found."

    response_parts = []
    for req in requirements_result.response_structure_requirements:
        response_parts.append(req.normalized_text)

    response_structure_summary = "\n\n".join(response_parts) if response_parts else "No response structure requirements found."

    extraction_data = {
        "language": extraction_result.language,
        "cpv_codes": extraction_result.cpv_codes,
        "other_codes": extraction_result.other_codes,
        "key_requirements_summary": extraction_result.key_requirements_summary,
    }

    query_parts = [
        "RFP RESPONSE GENERATION QUERY",
        "=" * 80,
        "",
        "SOLUTION REQUIREMENTS (What the buyer wants):",
        "-" * 80,
        solution_summary,
        "",
        "RESPONSE STRUCTURE REQUIREMENTS (How to respond):",
        "-" * 80,
        response_structure_summary,
        "",
        "EXTRACTION DATA:",
        "-" * 80,
        f"Language: {extraction_result.language}",
        f"CPV Codes: {', '.join(extraction_result.cpv_codes) if extraction_result.cpv_codes else 'None'}",
        f"Other Codes: {', '.join(extraction_result.other_codes) if extraction_result.other_codes else 'None'}",
        "",
        "KEY REQUIREMENTS SUMMARY:",
        extraction_result.key_requirements_summary if extraction_result.key_requirements_summary else "None",
    ]

    query_text = "\n".join(query_parts)

    logger.info(
        "Built query: %d solution reqs, %d response structure reqs, %d CPV codes, %d other codes",
        len(requirements_result.solution_requirements),
        len(requirements_result.response_structure_requirements),
        len(extraction_result.cpv_codes),
        len(extraction_result.other_codes),
    )

    return BuildQuery(
        query_text=query_text,
        solution_requirements_summary=solution_summary,
        response_structure_requirements_summary=response_structure_summary,
        extraction_data=extraction_data,
        confirmed=False,
    )

