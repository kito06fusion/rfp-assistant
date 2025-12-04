from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ExtractionResult(BaseModel):
    """Output model for the extraction agent."""

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
    """Output model for the scope agent."""

    essential_text: str = Field(description="Cleaned text containing only essential information")
    removed_text: str = Field(default="", description="Text that was removed as unnecessary")
    rationale: str = Field(default="", description="Explanation of scoping decisions")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return self.model_dump()


class RequirementItem(BaseModel):
    """Individual requirement item model."""

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
        """Convert to dictionary."""
        return self.model_dump()

