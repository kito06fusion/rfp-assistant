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
    removed_text: str = Field(description="Exact text snippets that are NOT necessary and should be removed")
    rationale: str = Field(default="", description="Explanation of what was identified as unnecessary")
    cleaned_text: str = Field(default="", description="Original text with removed parts deleted (computed after removal)")

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
    """Output model for the requirements agent."""

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

