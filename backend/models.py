from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ExtractionResult(BaseModel):
    translated_text: str = Field(default="", description="Translated text (empty for extraction agent)")
    language: str = Field(description="ISO language code (e.g., 'en', 'fr')")
    cpv_codes: List[str] = Field(default_factory=list, description="List of CPV codes")
    other_codes: List[str] = Field(default_factory=list, description="List of other classification codes")
    key_requirements_summary: str = Field(default="", description="Summary of key requirements as markdown bullets")
    raw_structured: Dict[str, Any] = Field(default_factory=dict, description="Additional structured metadata")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class ScopeResult(BaseModel):
    necessary_text: str = Field(description="Text that is necessary to create a response to this RFP")
    removed_text: str = Field(default="", description="Text that was removed/excluded as out-of-scope administrative content")
    rationale: str = Field(default="", description="Explanation of what was excluded and why")
    cleaned_text: str = Field(default="", description="Same as necessary_text (kept for backward compatibility)")
    comparison_agreement: bool = Field(default=True, description="Whether the comparison step agreed that necessary_text contains all necessary information")
    comparison_notes: str = Field(default="", description="Notes from the comparison validation step")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class RequirementItem(BaseModel):
    id: str = Field(description="Machine-friendly identifier (e.g., 'SOL-ARCH-01')")
    type: str = Field(
        default="unspecified",
        description="Requirement type: 'mandatory', 'optional', or 'unspecified'",
    )
    source_text: str = Field(description="Complete original text from the RFP document")
    normalized_text: str = Field(description="Concise, unambiguous restatement in clear English")
    category: str = Field(description="Category tag (e.g., 'Architecture', 'Security', 'SLA')")


class StructureDetectionResult(BaseModel):
    has_explicit_structure: bool = Field(
        description="True if RFP specifies explicit response structure with mandatory sections"
    )
    structure_type: str = Field(
        description="Type of structure: 'explicit', 'implicit', or 'none'"
    )
    detected_sections: List[str] = Field(
        default_factory=list,
        description="List of detected section names if explicit structure found"
    )
    structure_description: str = Field(
        default="",
        description="Description of the required structure"
    )
    confidence: float = Field(default=0.0, ge=0.0,le=1.0, description="Confidence score for structure detection (0.0-1.0)"
    )

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


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
    structure_detection: Optional[StructureDetectionResult] = Field(
        default=None,
        description="Structure detection result (populated after structure detection)"
    )

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class BuildQuery(BaseModel):
    query_text: str = Field(description="The consolidated build query text")
    solution_requirements_summary: str = Field(description="Summary of solution requirements")
    response_structure_requirements_summary: str = Field(description="Summary of response structure requirements")
    extraction_data: Dict[str, Any] = Field(description="Extraction agent data (codes, language, etc.)")
    confirmed: bool = Field(default=False, description="Whether the build query has been confirmed by human")


class ResponseResult(BaseModel):
    """Result from the response generation agent."""
    response_text: str = Field(description="The generated RFP response text")
    build_query_used: str = Field(description="The build query that was used")
    num_retrieved_chunks: int = Field(description="Number of RAG chunks used")
    notes: str = Field(default="", description="Additional notes or metadata")


class Question(BaseModel):
    """A question generated for unknown information."""
    question_id: str = Field(description="Unique identifier for the question")
    requirement_id: Optional[str] = Field(default=None, description="ID of the requirement this question relates to (None for build query questions)")
    question_text: str = Field(description="The actual question")
    context: str = Field(description="Why this question is important")
    category: str = Field(description="Category: technical, business, implementation, etc.")
    priority: str = Field(description="Priority: high, medium, or low")
    asked_at: Optional[str] = Field(default=None, description="Timestamp when question was asked")
    answered: bool = Field(default=False, description="Whether question has been answered")


class Answer(BaseModel):
    """An answer provided by the user."""
    question_id: str = Field(description="ID of the question being answered")
    answer_text: str = Field(description="The answer provided by the user")
    answered_at: Optional[str] = Field(default=None, description="Timestamp when answer was provided")


class ConversationContext(BaseModel):
    """Context for a conversation session."""
    session_id: str = Field(description="Unique session identifier")
    requirement_id: Optional[str] = Field(default=None, description="Current requirement being processed")
    questions: List[Question] = Field(default_factory=list, description="List of questions")
    answers: List[Answer] = Field(default_factory=list, description="List of answers")
    created_at: Optional[str] = Field(default=None, description="Session creation timestamp")
    
    def get_answer_for_question(self, question_id: str) -> Optional[str]:
        """Get answer text for a question ID."""
        for answer in self.answers:
            if answer.question_id == question_id:
                return answer.answer_text
        return None
    
    def get_qa_context(self) -> str:
        """Format Q&A pairs for inclusion in prompts."""
        if not self.answers:
            return ""
        
        parts = ["USER-PROVIDED INFORMATION (from Q&A):"]
        parts.append("=" * 80)
        
        for answer in self.answers:
            # Find corresponding question
            question = next((q for q in self.questions if q.question_id == answer.question_id), None)
            if question:
                parts.append(f"Q: {question.question_text}")
                parts.append(f"A: {answer.answer_text}")
                parts.append("")
        
        return "\n".join(parts)

