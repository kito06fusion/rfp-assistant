from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.agents.extraction_agent import run_extraction_agent
from backend.agents.scope_agent import run_scope_agent
from backend.agents.requirements_agent import run_requirements_agent
from backend.models import ExtractionResult, RequirementsResult, ScopeResult
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class RFPPipelineOutput(BaseModel):

    extraction: ExtractionResult
    scope: ScopeResult
    requirements: Optional[RequirementsResult] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "extraction": self.extraction.to_dict(),
            "scope": self.scope.to_dict(),
            "requirements": self.requirements.to_dict() if self.requirements else None,
        }


def run_rfp_pipeline(rfp_text: str, request_id: Optional[str] = None) -> RFPPipelineOutput:
    rid = request_id or "no-request-id"
    logger.info("REQUEST %s: step 1/3 – extraction agent", rid)
    extraction_res = run_extraction_agent(rfp_text)
    logger.info(
        "REQUEST %s: extraction complete (lang=%s, cpv=%d, other_codes=%d)",
        rid,
        extraction_res.language,
        len(extraction_res.cpv_codes),
        len(extraction_res.other_codes),
    )
    logger.info("REQUEST %s: step 2/3 – scope agent", rid)
    scope_res = run_scope_agent(translated_text=rfp_text)
    logger.info(
        "REQUEST %s: scope complete (necessary_chars=%d, cleaned_chars=%d, comparison_agreement=%s)",
        rid,
        len(scope_res.necessary_text or ""),
        len(scope_res.cleaned_text or ""),
        scope_res.comparison_agreement,
    )

    # NOTE (human-in-the-loop):

    logger.info("REQUEST %s: step 3/3 – requirements agent", rid)
    requirements_res = run_requirements_agent(
        essential_text=scope_res.cleaned_text,
        structured_info={},
    )
    logger.info(
        "REQUEST %s: requirements complete (solution=%d, response_structure=%d)",
        rid,
        len(requirements_res.solution_requirements),
        len(requirements_res.response_structure_requirements),
    )
    return RFPPipelineOutput(
        extraction=extraction_res,
        scope=scope_res,
        requirements=requirements_res,
    )


