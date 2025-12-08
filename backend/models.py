from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ExtractionResult(BaseModel):
    translated_text: str = Field(default="", description="Translated text (empty for extraction agent)")
    language: str = Field(description="ISO language code (e.g., 'en', 'fr')")
    cpv_codes: List[str] = Field(default_factory=list, description="List of CPV codes")
    other_codes: List[str] = Field(default_factory=list, description="List of other classification codes")
    key_requirements_summary: str = Field(default="", description="Summary of key requirements as markdown bullets")
    raw_structured: Dict[str, Any] = Field(default_factory=dict, description="Additional structured metadata")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return self.model_dump()


class ScopeResult(BaseModel):
    necessary_text: str = Field(description="Text that is necessary to create a response to this RFP")
    removed_text: str = Field(default="", description="Text that was removed/excluded as out-of-scope administrative content")
    rationale: str = Field(default="", description="Explanation of what was excluded and why")
    cleaned_text: str = Field(default="", description="Same as necessary_text (kept for backward compatibility)")
    comparison_agreement: bool = Field(default=True, description="Whether the comparison step agreed that necessary_text contains all necessary information")
    comparison_notes: str = Field(default="", description="Notes from the comparison validation step")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return self.model_dump()


class RequirementItem(BaseModel):
    id: str = Field(description="Machine-friendly identifier (e.g., 'SOL-ARCH-01')")
    type: str = Field(description="Requirement type: 'mandatory', 'optional', or 'unspecified'")
    source_text: str = Field(description="Complete original text from the RFP document")
    normalized_text: str = Field(description="Concise, unambiguous restatement in clear English")
    category: str = Field(description="Category tag (e.g., 'Architecture', 'Security', 'SLA')")


class RequirementsResult(BaseModel):
    solution_requirements: List[RequirementItem] = Field(
        default_factory=list,
        description="List of solution requirements (what the buyer wants)",
    )
    response_structure_requirements: List[RequirementItem] = Field(
        default_factory=list,
        description="List of response structure requirements (how to respond)",
    )
    notes: str = Field(default="", description="Clarifying comments or assumptions")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

