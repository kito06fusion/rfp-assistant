from __future__ import annotations
import functools
import json
import logging
from typing import Dict, Any

from backend.models import (
    ExtractionResult,
    RequirementsResult,
    BuildQuery,
    RequirementItem,
)

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=256)
#function to construct a BuildQuery for a single requirement (cached)
def _build_query_for_single_requirement_cached(
    extraction_json: str,
    requirement_json: str,
    response_structure_json: str,
) -> BuildQuery:
    extraction_result = ExtractionResult(**json.loads(extraction_json))
    single_requirement = RequirementItem(**json.loads(requirement_json))
    all_response_structure_requirements = [
        RequirementItem(**r) for r in json.loads(response_structure_json)
    ]
    
    logger.info("Building query for single requirement: %s", single_requirement.id)

    solution_summary = single_requirement.source_text

    response_parts = []
    for req in all_response_structure_requirements:
        response_parts.append(req.source_text)

    response_structure_summary = "\n\n".join(response_parts) if response_parts else "No response structure requirements found."

    extraction_data = {
        "language": extraction_result.language,
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
        "",
        "KEY REQUIREMENTS SUMMARY:",
        extraction_result.key_requirements_summary if extraction_result.key_requirements_summary else "None",
    ]

    query_text = "\n".join(query_parts)

    logger.info(
        "Built query for requirement %s: %d response structure reqs",
        single_requirement.id,
        len(all_response_structure_requirements),
    )

    return BuildQuery(
        query_text=query_text,
        solution_requirements_summary=solution_summary,
        response_structure_requirements_summary=response_structure_summary,
        extraction_data=extraction_data,
        confirmed=False,
    )

#function to prepare a BuildQuery object for a single requirement (wrapper with caching)
def build_query_for_single_requirement(
    extraction_result: ExtractionResult,
    single_requirement: RequirementItem,
    all_response_structure_requirements: list[RequirementItem],
) -> BuildQuery:
    extraction_json = json.dumps(extraction_result.model_dump(), sort_keys=True)
    requirement_json = json.dumps(single_requirement.model_dump(), sort_keys=True)
    response_structure_json = json.dumps(
        [r.model_dump() for r in all_response_structure_requirements],
        sort_keys=True
    )
    
    cache_info = _build_query_for_single_requirement_cached.cache_info()
    logger.info(
        "Build query (single): starting (cache_hits=%d, cache_misses=%d, cache_size=%d/%d)",
        cache_info.hits,
        cache_info.misses,
        cache_info.currsize,
        cache_info.maxsize,
    )
    
    result = _build_query_for_single_requirement_cached(
        extraction_json,
        requirement_json,
        response_structure_json,
    )
    
    new_cache_info = _build_query_for_single_requirement_cached.cache_info()
    if new_cache_info.hits > cache_info.hits:
        logger.info("Build query (single): cache HIT - returned cached result")
    else:
        logger.info("Build query (single): cache MISS - processed new request")
    
    return result

#function to build a full BuildQuery from extraction and requirements (cached)
@functools.lru_cache(maxsize=128)
def _build_query_cached(
    extraction_json: str,
    requirements_json: str,
) -> BuildQuery:
    extraction_result = ExtractionResult(**json.loads(extraction_json))
    requirements_result = RequirementsResult(**json.loads(requirements_json))
    
    logger.info("Building query from extraction and requirements data")

    solution_parts = []
    for req in requirements_result.solution_requirements:
        solution_parts.append(f"[{req.id}] {req.source_text}")

    solution_summary = "\n".join(solution_parts) if solution_parts else "No solution requirements found."

    response_parts = []
    for req in requirements_result.response_structure_requirements:
        response_parts.append(f"[{req.id}] {req.source_text}")

    response_structure_summary = "\n".join(response_parts) if response_parts else "No response structure requirements found."

    extraction_data = {
        "language": extraction_result.language,
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
        "",
        "KEY REQUIREMENTS SUMMARY:",
        extraction_result.key_requirements_summary if extraction_result.key_requirements_summary else "None",
    ]

    query_text = "\n".join(query_parts)

    logger.info(
        "Built query: %d solution reqs, %d response structure reqs",
        len(requirements_result.solution_requirements),
        len(requirements_result.response_structure_requirements),
    )

    return BuildQuery(
        query_text=query_text,
        solution_requirements_summary=solution_summary,
        response_structure_requirements_summary=response_structure_summary,
        extraction_data=extraction_data,
        confirmed=False,
    )

#function to build the overall BuildQuery (wrapper that uses cached builder)
def build_query(
    extraction_result: ExtractionResult,
    requirements_result: RequirementsResult,
) -> BuildQuery:
    extraction_json = json.dumps(extraction_result.model_dump(), sort_keys=True)
    requirements_json = json.dumps(requirements_result.model_dump(), sort_keys=True)
    
    cache_info = _build_query_cached.cache_info()
    logger.info(
        "Build query: starting (cache_hits=%d, cache_misses=%d, cache_size=%d/%d)",
        cache_info.hits,
        cache_info.misses,
        cache_info.currsize,
        cache_info.maxsize,
    )
    
    result = _build_query_cached(extraction_json, requirements_json)
    
    new_cache_info = _build_query_cached.cache_info()
    if new_cache_info.hits > cache_info.hits:
        logger.info("Build query: cache HIT - returned cached result")
    else:
        logger.info("Build query: cache MISS - processed new request")
    
    return result

