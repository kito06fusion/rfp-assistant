from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.pipeline.text_extraction import extract_text_from_file
from backend.agents.extraction_agent import run_extraction_agent
from backend.agents.scope_agent import run_scope_agent
from backend.agents.requirements_agent import run_requirements_agent
from backend.agents.build_query import build_query, build_query_for_single_requirement
from backend.agents.response_agent import run_response_agent
from backend.agents.structure_detection_agent import detect_structure
from backend.agents.structured_response_agent import run_structured_response_agent
from backend.agents.question_agent import (
    analyze_requirements_for_questions,
    analyze_build_query_for_questions,
    infer_answered_questions_from_answer,
)
from backend.agents.quality_agent import assess_response_quality
from backend.rag import RAGSystem
from backend.models import (
    ExtractionResult,
    RequirementsResult,
    StructureDetectionResult,
    ScopeResult,
    Question,
    Answer,
    ConversationContext,
)
from backend.knowledge_base import FusionAIxKnowledgeBase
from backend.knowledge_base.company_kb import CompanyKnowledgeBase


def _setup_rag_and_kb(use_rag: bool) -> tuple[Optional[RAGSystem], FusionAIxKnowledgeBase]:
    """Setup RAG system and knowledge base."""
    rag_system = None
    if use_rag:
        try:
            # Use project-root absolute paths so RAG always points to the correct docs folder
            project_root = Path(__file__).parent.parent
            docs_folder = project_root / "docs"
            index_path = project_root / "rag_index"
            rag_system = RAGSystem(docs_folder=str(docs_folder), index_path=str(index_path))
            try:
                rag_system.load_index()
                stats = rag_system.get_stats()
                logger.info(
                    "RAG loaded existing index successfully | built=%s, docs=%s, vectors=%s, dim=%s, model=%s",
                    stats.get("index_built"),
                    stats.get("num_documents"),
                    stats.get("num_vectors"),
                    stats.get("embedding_dimension"),
                    stats.get("embedding_model"),
                )
            except FileNotFoundError:
                logger.info(
                    "RAG index not found. Attempting to build index from docs folder '%s'...",
                    "docs",
                )
                try:
                    rag_system.build_index()
                    stats = rag_system.get_stats()
                    logger.info(
                        "RAG index built successfully from docs/ | docs=%s, vectors=%s, dim=%s, model=%s",
                        stats.get("num_documents"),
                        stats.get("num_vectors"),
                        stats.get("embedding_dimension"),
                        stats.get("embedding_model"),
                    )
                except ValueError as build_err:
                    logger.warning(
                        "Failed to build RAG index: %s. RAG system not available. "
                        "Make sure you have documents (PDF, DOCX, TXT) in the 'docs' folder. "
                        "Continuing without RAG.",
                        str(build_err)
                    )
                    rag_system = None
        except Exception as rag_exc:
            logger.warning("Failed to load/build RAG system: %s. Continuing without RAG.", rag_exc)
            rag_system = None
    
    knowledge_base = get_fusionaix_kb()
    logger.info(
        "Using fusionAIx knowledge base: %d capabilities, %d case studies, %d accelerators",
        len(knowledge_base.capabilities),
        len(knowledge_base.case_studies),
        len(knowledge_base.accelerators),
    )
    return rag_system, knowledge_base


def _enrich_build_query_with_rag(
    build_query: BuildQuery,
    requirements_result: RequirementsResult,
    rag_contexts_by_req: Dict[str, str],
) -> BuildQuery:
    """
    Enrich build query text with RAG-supported information per requirement.
    This runs after question generation so the build query reflects what is already
    known from prior RFPs.
    """
    if not rag_contexts_by_req:
        return build_query

    logger.info(
        "Enriching build query with RAG for %d requirement(s)",
        len(rag_contexts_by_req),
    )

    # Build a mapping from requirement_id to normalized_text for display
    req_text_by_id: Dict[str, str] = {
        req.id: req.normalized_text for req in requirements_result.solution_requirements
    }

    base_text = build_query.query_text or ""

    rag_section_lines: List[str] = []
    rag_section_lines.append("")
    rag_section_lines.append("=" * 80)
    rag_section_lines.append("RAG-SUPPORTED REQUIREMENTS (information already known from prior RFPs)")
    rag_section_lines.append("=" * 80)
    rag_section_lines.append("")

    for req_id, rag_ctx in rag_contexts_by_req.items():
        full_text = rag_ctx.strip()
        req_text = req_text_by_id.get(req_id, "")
        rag_section_lines.append(f"Requirement ID: {req_id}")
        if req_text:
            rag_section_lines.append(f"Requirement: {req_text}")
        rag_section_lines.append("RAG Evidence:")
        rag_section_lines.append(full_text if full_text else "[No RAG evidence text available]")
        rag_section_lines.append("--- END RAG EVIDENCE ---")
        rag_section_lines.append("")

    enriched_text = base_text.rstrip() + "\n" + "\n".join(rag_section_lines)
    build_query.query_text = enriched_text
    return build_query


def validate_before_generation(
    extraction_result: ExtractionResult,
    requirements_result: RequirementsResult,
) -> List[str]:
    """
    Quick validation before expensive LLM calls.
    Returns list of error messages (empty if all checks pass).
    """
    errors = []
    
    if not extraction_result.language:
        errors.append("Extraction result missing language")
    if not isinstance(extraction_result.language, str) or len(extraction_result.language) < 2:
        errors.append(f"Invalid language code: {extraction_result.language}")
    
    if not requirements_result.solution_requirements:
        errors.append("No solution requirements found")
        return errors  # Early return - can't proceed without requirements
    
    for idx, req in enumerate(requirements_result.solution_requirements, 1):
        if not req.id or not req.id.strip():
            errors.append(f"Solution requirement {idx} missing ID")
        if not req.normalized_text or not req.normalized_text.strip():
            errors.append(f"Solution requirement {idx} ({req.id}) missing normalized_text")
        if not req.source_text or not req.source_text.strip():
            errors.append(f"Solution requirement {idx} ({req.id}) missing source_text")
        if not req.category or not req.category.strip():
            errors.append(f"Solution requirement {idx} ({req.id}) missing category")
        if req.type not in ["mandatory", "optional", "unspecified"]:
            errors.append(f"Solution requirement {idx} ({req.id}) has invalid type: {req.type}")
        if len(req.normalized_text) < 10:
            errors.append(f"Solution requirement {idx} ({req.id}) normalized_text too short (likely incomplete)")
    
    if not requirements_result.response_structure_requirements:
        logger.warning("No response structure requirements found - responses may lack structure guidance")
    else:
        for idx, req in enumerate(requirements_result.response_structure_requirements, 1):
            if not req.id or not req.id.strip():
                errors.append(f"Response structure requirement {idx} missing ID")
            if not req.normalized_text or not req.normalized_text.strip():
                errors.append(f"Response structure requirement {idx} ({req.id}) missing normalized_text")
            if not req.source_text or not req.source_text.strip():
                errors.append(f"Response structure requirement {idx} ({req.id}) missing source_text")
    
    if requirements_result.solution_requirements:
        try:
            test_build_query = build_query_for_single_requirement(
                extraction_result=extraction_result,
                single_requirement=requirements_result.solution_requirements[0],
                all_response_structure_requirements=requirements_result.response_structure_requirements,
            )
            if not test_build_query.query_text or len(test_build_query.query_text) < 100:
                errors.append("Build query test failed - generated query text too short")
            if not test_build_query.solution_requirements_summary:
                errors.append("Build query test failed - missing solution requirements summary")
        except Exception as e:
            errors.append(f"Build query test failed: {str(e)}")
    
    solution_ids = [req.id for req in requirements_result.solution_requirements]
    if len(solution_ids) != len(set(solution_ids)):
        duplicates = [id for id in solution_ids if solution_ids.count(id) > 1]
        errors.append(f"Duplicate solution requirement IDs found: {set(duplicates)}")
    
    response_ids = [req.id for req in requirements_result.response_structure_requirements]
    if len(response_ids) != len(set(response_ids)):
        duplicates = [id for id in response_ids if response_ids.count(id) > 1]
        errors.append(f"Duplicate response structure requirement IDs found: {set(duplicates)}")
    
    return errors


LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


app = FastAPI(title="RFP Assistant Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files from frontend
project_root = Path(__file__).parent.parent
frontend_dist = project_root / "frontend" / "dist"
frontend_src = project_root / "frontend" / "src"

# Mount static assets
if frontend_dist.exists() and (frontend_dist / "index.html").exists():
    # Production: serve from dist
    if (frontend_dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")
    logger.info("Serving frontend from dist directory (production build)")
elif frontend_src.exists():
    # Development: serve source files directly
    app.mount("/src", StaticFiles(directory=str(frontend_src)), name="src")
    if (frontend_src.parent / "public").exists():
        app.mount("/public", StaticFiles(directory=str(frontend_src.parent / "public")), name="public")
    logger.info("Serving frontend from src directory (development mode - build frontend for production)")

_fusionaix_kb: FusionAIxKnowledgeBase | None = None

def get_fusionaix_kb() -> FusionAIxKnowledgeBase:
    """Get or create fusionAIx knowledge base instance."""
    global _fusionaix_kb
    if _fusionaix_kb is None:
        logger.info("Initializing fusionAIx knowledge base")
        _fusionaix_kb = FusionAIxKnowledgeBase()
        logger.info(
            "Knowledge base loaded: %d capabilities, %d case studies, %d accelerators",
            len(_fusionaix_kb.capabilities),
            len(_fusionaix_kb.case_studies),
            len(_fusionaix_kb.accelerators),
        )
    return _fusionaix_kb


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Serve the frontend index.html file."""
    project_root = Path(__file__).resolve().parent.parent
    # Try dist first (production), then regular frontend folder
    index_path = project_root / "frontend" / "dist" / "index.html"
    if not index_path.exists():
        index_path = project_root / "frontend" / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found. Please build the frontend first: npm run build")
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.post("/process-rfp")
async def process_rfp(file: UploadFile = File(...)) -> Dict[str, Any]:
    request_id = str(uuid.uuid4())
    logger.info("REQUEST %s: /process-rfp file=%s", request_id, file.filename)

    suffix = Path(file.filename).suffix.lower()
    # Supported input types: PDF, Word (DOCX/DOC), Excel (XLS/XLSX), and plain text
    if suffix not in {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".txt"}:
        logger.warning("REQUEST %s: unsupported file type %s", request_id, suffix)
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported file type. Please upload one of: "
                "PDF, DOCX, DOC, XLSX, XLS, or TXT."
            ),
        )

    temp_path = Path("/tmp") / f"{request_id}_{file.filename}"
    bytes_written = 0
    try:
        with open(temp_path, "wb") as f:
            while True:
                chunk = await file.read(2 * 1024 * 1024)  # 2 MB chunks for better performance
                if not chunk:
                    break
                f.write(chunk)
                bytes_written += len(chunk)
        logger.info(
            "REQUEST %s: streamed upload to temp file %s (%d bytes)",
            request_id,
            temp_path,
            bytes_written,
        )
    except Exception as e:
        logger.exception("REQUEST %s: failed to write uploaded file to disk: %s", request_id, e)
        raise HTTPException(status_code=500, detail="Failed to process uploaded file.") from e

    t0 = time.time()
    try:
        text = extract_text_from_file(temp_path)
        logger.info(
            "REQUEST %s: extracted %d characters of text", request_id, len(text)
        )
    finally:
        try:
            temp_path.unlink(missing_ok=True)
            logger.debug("REQUEST %s: removed temp file %s", request_id, temp_path)
        except Exception:
            logger.exception(
                "REQUEST %s: failed to remove temp file %s", request_id, temp_path
            )

        logger.info(
            "REQUEST %s: OCR extracted %d characters of text from document",
            request_id,
            len(text),
        )

    if not text.strip():
        logger.warning("REQUEST %s: no text extracted from file", request_id)
        raise HTTPException(status_code=400, detail="No text could be extracted from file.")

    try:
        extraction_res = run_extraction_agent(text)
    except Exception as exc:
        elapsed = time.time() - t0
        logger.exception(
            "REQUEST %s: extraction agent failed after %.2fs: %s",
            request_id,
            elapsed,
            exc,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Extraction agent failed for request {request_id}. Check server logs.",
        ) from exc

    logger.info(
        "REQUEST %s: extraction agent finished (lang=%s, cpv=%d, other_codes=%d)",
        request_id,
        extraction_res.language,
        len(extraction_res.cpv_codes),
        len(extraction_res.other_codes),
    )
    try:
        scope_res = run_scope_agent(translated_text=text)
    except Exception as exc:
        elapsed = time.time() - t0
        logger.exception(
            "REQUEST %s: scope agent failed after %.2fs: %s", request_id, elapsed, exc
        )
        raise HTTPException(
            status_code=500,
            detail=f"Scope agent failed for request {request_id}. Check server logs.",
        ) from exc
    elapsed = time.time() - t0
    logger.info(
        "REQUEST %s: scope agent finished (necessary_chars=%d, removed_chars=%d, cleaned_chars=%d, comparison_agreement=%s)",
        request_id,
        len(scope_res.necessary_text or ""),
        len(scope_res.removed_text or ""),
        len(scope_res.cleaned_text or ""),
        scope_res.comparison_agreement,
    )
    logger.info("REQUEST %s: extraction + scope completed in %.2fs", request_id, elapsed)
    response: Dict[str, Any] = {
        "extraction": extraction_res.to_dict(),
        "scope": scope_res.to_dict(),
        "requirements": None,
        "ocr_source_text": text,
    }
    response["extraction"]["ocr_text"] = text
    return response

class RequirementsRequest(BaseModel):
    essential_text: str


class UpdateScopeRequest(BaseModel):
    """Manual edits to scoped text before confirmation."""
    necessary_text: str
    removed_text: str | None = None
    rationale: str | None = None


class UpdateRequirementsRequest(BaseModel):
    """Manual edits to requirements before build-query."""
    requirements: Dict[str, Any]

@app.post("/run-requirements")
async def run_requirements(req: RequirementsRequest) -> Dict[str, Any]:
    logger.info(
        "Requirements endpoint called (essential_chars=%d)", len(req.essential_text)
    )
    try:
        result = run_requirements_agent(essential_text=req.essential_text, structured_info={})
        
        # Run structure detection after requirements are extracted
        logger.info("Running structure detection on %d response structure requirements", 
                   len(result.response_structure_requirements))
        structure_detection_dict = detect_structure(result.response_structure_requirements)
        structure_detection = StructureDetectionResult(**structure_detection_dict)
        result.structure_detection = structure_detection
        
        logger.info(
            "Structure detection completed: explicit=%s, type=%s, sections=%d, confidence=%.2f",
            structure_detection.has_explicit_structure,
            structure_detection.structure_type,
            len(structure_detection.detected_sections),
            structure_detection.confidence,
        )
    except Exception as exc:
        logger.exception("Requirements agent failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Requirements agent failed. Check server logs.",
        ) from exc
    logger.info(
        "Requirements agent completed (solution=%d, response_structure=%d)",
        len(result.solution_requirements),
        len(result.response_structure_requirements),
    )
    return result.to_dict()


@app.post("/update-scope")
async def update_scope(req: UpdateScopeRequest) -> Dict[str, Any]:
    """
    Accept manually edited scope text before confirmation.
    This does not re-run the scope agent; it simply persists the edited fields
    in the same shape as ScopeResult for downstream steps.
    """
    logger.info(
        "Update scope endpoint called (necessary_chars=%d)",
        len(req.necessary_text),
    )
    scope = ScopeResult(
        necessary_text=req.necessary_text,
        removed_text=req.removed_text or "",
        rationale=req.rationale or "Manually edited by user.",
        cleaned_text=req.necessary_text,
        comparison_agreement=True,
        comparison_notes="Manually edited and accepted by user.",
    )
    return scope.to_dict()


@app.post("/update-requirements")
async def update_requirements(req: UpdateRequirementsRequest) -> Dict[str, Any]:
    """
    Accept manually edited requirements JSON before build-query.
    """
    logger.info("Update requirements endpoint called")
    try:
        # Validate structure using RequirementsResult
        result = RequirementsResult(**req.requirements)
        return result.to_dict()
    except Exception as exc:
        logger.exception("Update requirements failed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid requirements payload: {str(exc)}",
        ) from exc

class BuildQueryRequest(BaseModel):
    extraction: Dict[str, Any]
    requirements: Dict[str, Any]


@app.post("/build-query")
async def build_query_endpoint(req: BuildQueryRequest) -> Dict[str, Any]:
    """Build consolidated query from extraction and requirements."""
    logger.info("Build query endpoint called")
    try:
        extraction_result = ExtractionResult(**req.extraction)
        requirements_result = RequirementsResult(**req.requirements)
        query = build_query(extraction_result, requirements_result)
        return query.model_dump()
    except Exception as exc:
        logger.exception("Build query failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Build query failed. Check server logs.",
        ) from exc


class GenerateResponseRequest(BaseModel):
    extraction: Dict[str, Any]
    requirements: Dict[str, Any]
    use_rag: bool = True
    num_retrieval_chunks: int = 5
    session_id: Optional[str] = None  # Chat session ID for Q&A context


@app.post("/generate-response")
async def generate_response_endpoint(req: GenerateResponseRequest) -> Dict[str, Any]:
    """Generate RFP response - uses structured response if explicit structure detected, otherwise per-requirement."""
    logger.info("Generate response endpoint called (use_rag=%s)", req.use_rag)
    try:
        from backend.models import BuildQuery, ExtractionResult, RequirementsResult
        
        extraction_result = ExtractionResult(**req.extraction)
        requirements_result = RequirementsResult(**req.requirements)
        
        if not requirements_result.solution_requirements:
            raise HTTPException(
                status_code=400,
                detail="No solution requirements found. Cannot generate response.",
            )
        
        # Check if structure detection was done, if not, run it now
        if requirements_result.structure_detection is None:
            logger.info("Structure detection not found in requirements, running now...")
            structure_detection_dict = detect_structure(requirements_result.response_structure_requirements)
            requirements_result.structure_detection = StructureDetectionResult(**structure_detection_dict)
        
        structure_detection = requirements_result.structure_detection
        
        # Conditional routing: structured response vs per-requirement response
        if structure_detection.has_explicit_structure and structure_detection.confidence >= 0.6:
            logger.info(
                "=" * 80
            )
            logger.info(
                "EXPLICIT STRUCTURE DETECTED - Using structured response generation"
            )
            logger.info(
                "Structure: %s (%d sections, confidence=%.2f)",
                structure_detection.structure_type,
                len(structure_detection.detected_sections),
                structure_detection.confidence,
            )
            logger.info(
                "=" * 80
            )
            return await _generate_structured_response(
                extraction_result=extraction_result,
                requirements_result=requirements_result,
                structure_detection=structure_detection,
                use_rag=req.use_rag,
                num_retrieval_chunks=req.num_retrieval_chunks,
                session_id=req.session_id,
            )
        else:
            logger.info(
                "=" * 80
            )
            logger.info(
                "NO EXPLICIT STRUCTURE - Using per-requirement response generation"
            )
            logger.info(
                "Structure type: %s, confidence: %.2f",
                structure_detection.structure_type if structure_detection else "none",
                structure_detection.confidence if structure_detection else 0.0,
            )
            logger.info(
                "=" * 80
            )
            return await _generate_per_requirement_response(
                extraction_result=extraction_result,
                requirements_result=requirements_result,
                use_rag=req.use_rag,
                num_retrieval_chunks=req.num_retrieval_chunks,
                session_id=req.session_id,
            )
    except HTTPException:
        raise
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        logger.exception("Response generation failed completely: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Response generation failed. Check server logs. Error: {str(exc)}",
        ) from exc


async def _generate_structured_response(
    extraction_result: ExtractionResult,
    requirements_result: RequirementsResult,
    structure_detection: StructureDetectionResult,
    use_rag: bool,
    num_retrieval_chunks: int,
    session_id: Optional[str] = None,
) -> Response:
    """Generate structured response following RFP-specified structure."""
    rag_system, knowledge_base = _setup_rag_and_kb(use_rag)
    
    logger.info("=" * 80)
    logger.info("Running pre-flight validation before structured response generation...")
    validation_errors = validate_before_generation(
        extraction_result=extraction_result,
        requirements_result=requirements_result,
    )
    if validation_errors:
        error_msg = "Pre-flight validation failed. Please fix the following issues:\n" + "\n".join(f"  - {err}" for err in validation_errors)
        logger.error(error_msg)
        raise HTTPException(
            status_code=400,
            detail=error_msg,
        )
    logger.info("✓ Pre-flight validation passed - all checks OK")
    logger.info("=" * 80)
    
    logger.info("Generating structured response...")
    start_time = time.time()
    
    try:
        # Get Q&A context if session_id provided
        qa_context = ""
        if session_id and session_id in _conversation_sessions:
            context = _conversation_sessions[session_id]
            qa_context = context.get_qa_context()
            logger.info("Including Q&A context from session %s (%d answers)", session_id, len(context.answers))
        
        result = run_structured_response_agent(
            extraction_result=extraction_result,
            requirements_result=requirements_result,
            structure_detection=structure_detection,
            rag_system=rag_system,
            num_retrieval_chunks=num_retrieval_chunks,
            knowledge_base=knowledge_base,
            qa_context=qa_context,
        )
        
        # Convert structured response to individual_responses format for document generation
        # Split by sections if possible, or create single response
        individual_responses = [{
            "requirement_id": "STRUCTURED",
            "requirement_text": f"Complete structured response following: {', '.join(structure_detection.detected_sections)}",
            "key_phrase": structure_detection.detected_sections[0] if structure_detection.detected_sections else "Structured Response",
            "response": result.response_text,
            "notes": result.notes,
        }]
        
        total_elapsed = time.time() - start_time
        logger.info("Structured response generated in %.2f seconds (length=%d chars)", total_elapsed, len(result.response_text))
        
        # Generate Word (DOCX) document instead of PDF for editable output
        from backend.document_formatter import generate_rfp_docx
        if not generate_rfp_docx:
            logger.error("DOCX generation not available. Install python-docx to enable Word export.")
            raise HTTPException(
                status_code=500,
                detail="DOCX generation not available. Install python-docx to enable Word export.",
            )
        
        rfp_title = f"RFP Response (Structured)"
        if extraction_result.key_requirements_summary:
            rfp_title = f"RFP Response (Structured) - {extraction_result.key_requirements_summary[:50]}..."
        
        project_root = Path(__file__).parent.parent
        output_dir = project_root / "output" / "docx"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = int(time.time())
        docx_filename = f"rfp_response_structured_{extraction_result.language}_{timestamp}.docx"
        docx_path = output_dir / docx_filename
        
        docx_bytes = generate_rfp_docx(
            individual_responses=individual_responses,
            requirements_result=requirements_result,
            extraction_result=extraction_result,
            rfp_title=rfp_title,
            output_path=docx_path,
        )
        
        docx_bytes = docx_path.read_bytes()
        logger.info("DOCX generated successfully: %d bytes", len(docx_bytes))
        
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f'attachment; filename="{docx_filename}"',
                "Content-Length": str(len(docx_bytes)),
            }
        )
    except Exception as exc:
        logger.exception("Structured response generation failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Structured response generation failed: {str(exc)}",
        ) from exc


async def _generate_per_requirement_response(
    extraction_result: ExtractionResult,
    requirements_result: RequirementsResult,
    use_rag: bool,
    num_retrieval_chunks: int,
    session_id: Optional[str] = None,
) -> Response:
    """Generate per-requirement response (original flow)."""
    rag_system, knowledge_base = _setup_rag_and_kb(use_rag)
    
    # Get Q&A context if session_id provided
    qa_context = ""
    if session_id and session_id in _conversation_sessions:
        context = _conversation_sessions[session_id]
        qa_context = context.get_qa_context()
        logger.info("Including Q&A context from session %s (%d answers)", session_id, len(context.answers))
    
    logger.info("=" * 80)
    logger.info("Running pre-flight validation before response generation...")
    validation_errors = validate_before_generation(
        extraction_result=extraction_result,
        requirements_result=requirements_result,
    )
    if validation_errors:
        error_msg = "Pre-flight validation failed. Please fix the following issues:\n" + "\n".join(f"  - {err}" for err in validation_errors)
        logger.error(error_msg)
        raise HTTPException(
            status_code=400,
            detail=error_msg,
        )
    logger.info("✓ Pre-flight validation passed - all checks OK")
    logger.info("=" * 80)
    
    total_requirements = len(requirements_result.solution_requirements)
    logger.info("=" * 80)
    logger.info("Starting response generation for %d solution requirement(s)", total_requirements)
    logger.info("=" * 80)
    
    individual_responses = []
    successful_responses = 0
    failed_responses = 0
    start_time = time.time()
    partial_completion = False
    
    try:
        for idx, solution_req in enumerate(requirements_result.solution_requirements, 1):
            req_start_time = time.time()
            logger.info(
                "[%d/%d] Processing requirement: %s",
                idx,
                total_requirements,
                solution_req.id,
            )
            logger.info(
                "[%d/%d] Requirement text: %s",
                idx,
                total_requirements,
                solution_req.normalized_text[:100] + "..." if len(solution_req.normalized_text) > 100 else solution_req.normalized_text,
            )
            
            build_query_obj = build_query_for_single_requirement(
                extraction_result=extraction_result,
                single_requirement=solution_req,
                all_response_structure_requirements=requirements_result.response_structure_requirements,
            )
            build_query_obj.confirmed = True  # Auto-confirm for individual requirements
            
            try:
                result = run_response_agent(
                    build_query=build_query_obj,
                    rag_system=rag_system,
                    num_retrieval_chunks=num_retrieval_chunks,
                    knowledge_base=knowledge_base,
                    qa_context=qa_context,
                )
                words = solution_req.normalized_text.split()
                key_phrase = " ".join(words[:10]) + ("..." if len(words) > 10 else "")
                
                # Assess response quality
                quality_assessment = assess_response_quality(solution_req, result.response_text)
                
                individual_responses.append({
                    "requirement_id": solution_req.id,
                    "requirement_text": solution_req.normalized_text,
                    "key_phrase": key_phrase,
                    "response": result.response_text,
                    "notes": result.notes,
                    "quality": quality_assessment,
                })
                req_elapsed = time.time() - req_start_time
                successful_responses += 1
                logger.info(
                    "[%d/%d] ✓ SUCCESS: Generated response for requirement %s (length=%d chars, time=%.2fs)",
                    idx,
                    total_requirements,
                    solution_req.id,
                    len(result.response_text),
                    req_elapsed,
                )
                logger.info(
                    "[%d/%d] Progress: %d successful, %d failed, %d remaining",
                    idx,
                    total_requirements,
                    successful_responses,
                    failed_responses,
                    total_requirements - idx,
                )
            except Exception as req_exc:
                req_elapsed = time.time() - req_start_time
                failed_responses += 1
                logger.error(
                    "[%d/%d] ✗ FAILED: Requirement %s failed after %.2fs: %s",
                    idx,
                    total_requirements,
                    solution_req.id,
                    req_elapsed,
                    req_exc,
                )
                logger.exception(
                    "[%d/%d] Full error traceback for requirement %s:",
                    idx,
                    total_requirements,
                    solution_req.id,
                )
                words = solution_req.normalized_text.split()
                key_phrase = " ".join(words[:10]) + ("..." if len(words) > 10 else "")

                individual_responses.append({
                    "requirement_id": solution_req.id,
                    "requirement_text": solution_req.normalized_text,
                    "key_phrase": key_phrase,
                    "response": f"[ERROR: Failed to generate response for this requirement: {str(req_exc)}]",
                    "notes": f"Error: {str(req_exc)}",
                    "quality": {
                        "score": 0.0,
                        "completeness": "incomplete",
                        "relevance": "low",
                        "issues": [f"Generation failed: {str(req_exc)}"],
                        "suggestions": ["Fix the error and regenerate"],
                    },
                })
                logger.info(
                    "[%d/%d] Progress: %d successful, %d failed, %d remaining",
                    idx,
                    total_requirements,
                    successful_responses,
                    failed_responses,
                    total_requirements - idx,
                )

            del req_start_time, req_elapsed
    except KeyboardInterrupt:
        logger.warning("Response generation interrupted by user")
        partial_completion = True
        raise
    except Exception as catastrophic_error:
        logger.error(
            "Catastrophic error during response generation: %s",
            catastrophic_error,
        )
        logger.exception("Full traceback:")
        partial_completion = True
        
        if not individual_responses:
            if partial_completion:
                raise HTTPException(
                    status_code=500,
                    detail="Response generation failed before any responses could be generated. Check server logs.",
                )
        
        if partial_completion:
            logger.warning(
                "Response generation completed partially: %d/%d requirements processed",
                len(individual_responses),
                total_requirements,
            )
        
        combined_parts = []
        
        combined_parts.append("=" * 80)
        combined_parts.append("RFP RESPONSE DOCUMENT")
        combined_parts.append("=" * 80)
        combined_parts.append("")
        
        if requirements_result.response_structure_requirements:
            combined_parts.append("RESPONSE STRUCTURE REQUIREMENTS")
            combined_parts.append("-" * 80)
            for resp_req in requirements_result.response_structure_requirements:
                combined_parts.append(f"[{resp_req.type.upper()}] {resp_req.normalized_text}")
                combined_parts.append(f"Source: {resp_req.source_text}")
                combined_parts.append("")
            combined_parts.append("")
        
        combined_parts.append("SOLUTION REQUIREMENT RESPONSES")
        combined_parts.append("=" * 80)
        combined_parts.append("")
        
        for idx, resp_data in enumerate(individual_responses, 1):
            combined_parts.append(f"Requirement {idx}: {resp_data['requirement_id']}")
            combined_parts.append("-" * 80)
            combined_parts.append(f"Requirement: {resp_data['requirement_text']}")
            combined_parts.append("")
            combined_parts.append("Response:")
            combined_parts.append("-" * 40)
            combined_parts.append(resp_data['response'])
            combined_parts.append("")
            combined_parts.append("")
        
        combined_response = "\n".join(combined_parts)
        total_elapsed = time.time() - start_time
        
        logger.info(
            "=" * 80
        )
        logger.info(
            "Response generation completed:"
        )
        logger.info(
            "  Total requirements: %d",
            total_requirements,
        )
        logger.info(
            "  Successful responses: %d",
            successful_responses,
        )
        logger.info(
            "  Failed responses: %d",
            failed_responses,
        )
        logger.info(
            "  Success rate: %.1f%%",
            (successful_responses / total_requirements * 100) if total_requirements > 0 else 0.0,
        )
        logger.info(
            "  Total time: %.2f seconds",
            total_elapsed,
        )
        logger.info(
            "  Average time per requirement: %.2f seconds",
            total_elapsed / total_requirements if total_requirements > 0 else 0.0,
        )
        logger.info(
            "  Combined response length: %d characters",
            len(combined_response),
        )
        logger.info(
            "=" * 80
        )
        
        # Always generate an editable Word (DOCX) document
        logger.info("Generating DOCX document...")
        try:
            from backend.document_formatter import generate_rfp_docx
            if not generate_rfp_docx:
                raise ImportError("DOCX generation not available. Install python-docx.")
            
            rfp_title = f"RFP Response"
            if extraction_result.key_requirements_summary:
                rfp_title = f"RFP Response - {extraction_result.key_requirements_summary[:50]}..."
            
            logger.info("Generating DOCX with %d individual responses", len(individual_responses))
            docx_start_time = time.time()
            
            project_root = Path(__file__).parent.parent
            output_dir = project_root / "output" / "docx"
            output_dir.mkdir(parents=True, exist_ok=True)
            logger.info("DOCX output directory: %s (absolute: %s)", output_dir, output_dir.absolute())
            
            timestamp = int(time.time())
            docx_filename = f"rfp_response_{extraction_result.language}_{timestamp}.docx"
            docx_path = output_dir / docx_filename
            logger.info("DOCX will be saved to: %s", docx_path.absolute())
            
            docx_bytes = generate_rfp_docx(
                individual_responses=individual_responses,
                requirements_result=requirements_result,
                extraction_result=extraction_result,
                rfp_title=rfp_title,
                output_path=docx_path,
            )
            
            docx_bytes = docx_path.read_bytes()
            
            docx_elapsed = time.time() - docx_start_time
            docx_absolute_path = docx_path.absolute()
            logger.info(
                "DOCX generation completed successfully: %d bytes in %.2f seconds, saved to %s",
                len(docx_bytes),
                docx_elapsed,
                docx_absolute_path,
            )
            
            if not docx_path.exists():
                logger.error("DOCX file was not found after generation at: %s", docx_absolute_path)
                raise FileNotFoundError(f"DOCX was not saved to {docx_absolute_path}")
            
            return Response(
                content=docx_bytes,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={
                    "Content-Disposition": f'attachment; filename="{docx_filename}"',
                    "Content-Length": str(len(docx_bytes)),
                }
            )
        except ImportError as import_exc:
            logger.error("DOCX generation not available: %s", import_exc)
            raise HTTPException(
                status_code=500,
                detail="DOCX generation not available. python-docx dependency is missing. Check server logs.",
            ) from import_exc
        except Exception as docx_exc:
            logger.exception("DOCX generation failed: %s", docx_exc)
            raise HTTPException(
                status_code=500,
                detail=f"DOCX generation failed: {str(docx_exc)}",
            ) from docx_exc
    except KeyboardInterrupt:
        logger.warning("Response generation interrupted by user")
        partial_completion = True
        raise
    except Exception as catastrophic_error:
        logger.error("Catastrophic error during response generation: %s", catastrophic_error)
        logger.exception("Full traceback:")
        partial_completion = True
        if not individual_responses:
            raise HTTPException(
                status_code=500,
                detail="Response generation failed before any responses could be generated. Check server logs.",
            ) from catastrophic_error
    
    if not individual_responses:
        if partial_completion:
            raise HTTPException(
                status_code=500,
                detail="Response generation failed before any responses could be generated. Check server logs.",
            )
    
    if partial_completion:
        logger.warning(
            "Response generation completed partially: %d/%d requirements processed",
            len(individual_responses),
            total_requirements,
        )
    
    combined_parts = []
    combined_parts.append("=" * 80)
    combined_parts.append("RFP RESPONSE DOCUMENT")
    combined_parts.append("=" * 80)
    combined_parts.append("")
    
    if requirements_result.response_structure_requirements:
        combined_parts.append("RESPONSE STRUCTURE REQUIREMENTS")
        combined_parts.append("-" * 80)
        for resp_req in requirements_result.response_structure_requirements:
            combined_parts.append(f"[{resp_req.type.upper()}] {resp_req.normalized_text}")
            combined_parts.append(f"Source: {resp_req.source_text}")
            combined_parts.append("")
        combined_parts.append("")
    
    combined_parts.append("SOLUTION REQUIREMENT RESPONSES")
    combined_parts.append("=" * 80)
    combined_parts.append("")
    
    for idx, resp_data in enumerate(individual_responses, 1):
        combined_parts.append(f"Requirement {idx}: {resp_data['requirement_id']}")
        combined_parts.append("-" * 80)
        combined_parts.append(f"Requirement: {resp_data['requirement_text']}")
        combined_parts.append("")
        combined_parts.append("Response:")
        combined_parts.append("-" * 40)
        combined_parts.append(resp_data['response'])
        combined_parts.append("")
        combined_parts.append("")
    
    combined_response = "\n".join(combined_parts)
    total_elapsed = time.time() - start_time
    
    logger.info("=" * 80)
    logger.info("Response generation completed:")
    logger.info("  Total requirements: %d", total_requirements)
    logger.info("  Successful responses: %d", successful_responses)
    logger.info("  Failed responses: %d", failed_responses)
    logger.info("  Success rate: %.1f%%", (successful_responses / total_requirements * 100) if total_requirements > 0 else 0.0)
    logger.info("  Total time: %.2f seconds", total_elapsed)
    logger.info("  Average time per requirement: %.2f seconds", total_elapsed / total_requirements if total_requirements > 0 else 0.0)
    logger.info("  Combined response length: %d characters", len(combined_response))
    logger.info("=" * 80)
    
    # Generate Word (DOCX) document for editable output
    logger.info("Generating DOCX document...")
    try:
        from backend.document_formatter import generate_rfp_docx
        if not generate_rfp_docx:
            raise ImportError("DOCX generation not available. Install python-docx.")

        rfp_title = f"RFP Response"
        if extraction_result.key_requirements_summary:
            rfp_title = f"RFP Response - {extraction_result.key_requirements_summary[:50]}..."
        
        logger.info("Generating DOCX with %d individual responses", len(individual_responses))
        docx_start_time = time.time()
        
        project_root = Path(__file__).parent.parent
        output_dir = project_root / "output" / "docx"
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("DOCX output directory: %s (absolute: %s)", output_dir, output_dir.absolute())
        
        timestamp = int(time.time())
        docx_filename = f"rfp_response_{extraction_result.language}_{timestamp}.docx"
        docx_path = output_dir / docx_filename
        logger.info("DOCX will be saved to: %s", docx_path.absolute())
        
        docx_bytes = generate_rfp_docx(
            individual_responses=individual_responses,
            requirements_result=requirements_result,
            extraction_result=extraction_result,
            rfp_title=rfp_title,
            output_path=docx_path,
        )
        
        docx_bytes = docx_path.read_bytes()
        
        docx_elapsed = time.time() - docx_start_time
        docx_absolute_path = docx_path.absolute()
        logger.info(
            "DOCX generation completed successfully: %d bytes in %.2f seconds, saved to %s",
            len(docx_bytes),
            docx_elapsed,
            docx_absolute_path,
        )
        
        if not docx_path.exists():
            logger.error("DOCX file was not found after generation at: %s", docx_absolute_path)
            raise FileNotFoundError(f"DOCX was not saved to {docx_absolute_path}")
        
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f'attachment; filename="{docx_filename}"',
                "Content-Length": str(len(docx_bytes)),
            }
        )
    except ImportError as import_exc:
        logger.error("DOCX generation not available: %s", import_exc)
        raise HTTPException(
            status_code=500,
            detail="DOCX generation not available. python-docx dependency is missing. Check server logs.",
        ) from import_exc
    except Exception as docx_exc:
        logger.exception("DOCX generation failed: %s", docx_exc)
        raise HTTPException(
            status_code=500,
            detail=f"DOCX generation failed: {str(docx_exc)}",
        ) from docx_exc
        raise HTTPException(
            status_code=500,
            detail=f"Response generation failed. Check server logs. Error: {str(exc)}",
        ) from exc


# Chat/Question endpoints
_conversation_sessions: Dict[str, ConversationContext] = {}
_company_kb_instance: Optional[CompanyKnowledgeBase] = None

def get_company_kb() -> CompanyKnowledgeBase:
    """Get or create company knowledge base instance."""
    global _company_kb_instance
    if _company_kb_instance is None:
        logger.info("Initializing company knowledge base")
        _company_kb_instance = CompanyKnowledgeBase()
    return _company_kb_instance


class GenerateQuestionsRequest(BaseModel):
    requirements: Optional[Dict[str, Any]] = None
    build_query: Optional[Dict[str, Any]] = None


class EnrichBuildQueryRequest(BaseModel):
    build_query: Dict[str, Any]
    session_id: Optional[str] = None


@app.post("/generate-questions")
async def generate_questions_endpoint(req: GenerateQuestionsRequest) -> Dict[str, Any]:
    """Generate questions for unknown information in build query or requirements."""
    logger.info("Generate questions endpoint called")
    try:
        from backend.models import RequirementsResult, BuildQuery
        from backend.agents.question_agent import (
            analyze_build_query_for_questions, 
            analyze_requirements_for_questions,
            analyze_build_query_for_questions_legacy,
        )
        
        company_kb = get_company_kb()
        # Use RAG to avoid asking questions for information already present in prior RFPs
        rag_system, _ = _setup_rag_and_kb(use_rag=True)
        
        # Priority: analyze build query if provided, otherwise fall back to requirements
        if req.build_query:
            logger.info("Analyzing build query for questions")
            build_query_obj = BuildQuery(**req.build_query)
            
            # We need the requirements to analyze them individually
            # Get requirements from the request if available
            if req.requirements:
                requirements_result = RequirementsResult(**req.requirements)
                questions_list, rag_contexts_by_req = analyze_build_query_for_questions(
                    build_query_obj,
                    requirements_result,
                    company_kb,
                    max_questions_per_requirement=3,
                    rag_system=rag_system,
                )
                # Enrich build query with RAG-supported information
                enriched_build_query = _enrich_build_query_with_rag(
                    build_query_obj,
                    requirements_result,
                    rag_contexts_by_req,
                )
            else:
                # Fallback: analyze build query as a whole (less ideal)
                logger.warning("Requirements not provided with build query, analyzing build query as whole")
                questions_list = analyze_build_query_for_questions_legacy(
                    build_query_obj,
                    company_kb,
                    max_questions=20,
                )
            
            # Convert to Question objects
            all_questions = []
            questions_by_req = {}
            for idx, q in enumerate(questions_list):
                req_id = q.get("requirement_id")
                question = Question(
                    question_id=f"{req_id}-q-{idx}" if req_id else f"bq-q-{idx}",
                    requirement_id=req_id,
                    question_text=q["question_text"],
                    context=q.get("context", ""),
                    category=q.get("category", "general"),
                    priority=q.get("priority", "medium"),
                )
                all_questions.append(question.model_dump())
                
                # Group by requirement
                if req_id:
                    if req_id not in questions_by_req:
                        questions_by_req[req_id] = []
                    questions_by_req[req_id].append(q)
            
            logger.info("Generated %d questions from build query", len(all_questions))
            
            response_payload: Dict[str, Any] = {
                "questions": all_questions,
                "questions_by_requirement": questions_by_req,
            }
            # Include enriched build query if we had requirements (and thus RAG contexts)
            if req.requirements:
                response_payload["enriched_build_query"] = enriched_build_query.model_dump()
            return response_payload
        elif req.requirements:
            logger.info("Analyzing requirements for questions (legacy mode)")
            requirements_result = RequirementsResult(**req.requirements)
            
            # Generate questions for all solution requirements, using RAG to treat known info as answered
            questions_dict = analyze_requirements_for_questions(
                requirements_result.solution_requirements,
                company_kb,
                max_questions_per_requirement=3,
                rag_system=rag_system,
            )
            
            # Convert to list format for response
            all_questions = []
            for req_id, questions in questions_dict.items():
                for q in questions:
                    # q is already a dict from question_agent
                    question = Question(
                        question_id=f"{req_id}-q-{len(all_questions)}",
                        requirement_id=req_id,
                        question_text=q["question_text"],
                        context=q.get("context", ""),
                        category=q.get("category", "general"),
                        priority=q.get("priority", "medium"),
                    )
                    all_questions.append(question.model_dump())
            
            logger.info("Generated %d questions across %d requirements", len(all_questions), len(questions_dict))
            
            return {
                "questions": all_questions,
                "questions_by_requirement": {
                    req_id: questions  # questions are already dicts, no need to call model_dump()
                    for req_id, questions in questions_dict.items()
                },
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="Either 'build_query' or 'requirements' must be provided",
            )
    except Exception as exc:
        logger.exception("Generate questions failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Generate questions failed. Check server logs.",
        ) from exc


class CreateSessionRequest(BaseModel):
    requirement_id: Optional[str] = None


@app.post("/chat/session")
async def create_chat_session(req: CreateSessionRequest) -> Dict[str, Any]:
    """Create a new chat session."""
    session_id = str(uuid.uuid4())
    context = ConversationContext(
        session_id=session_id,
        requirement_id=req.requirement_id,
        created_at=datetime.now().isoformat(),
    )
    _conversation_sessions[session_id] = context
    logger.info("Created chat session: %s", session_id)
    return {"session_id": session_id}


class AddQuestionsRequest(BaseModel):
    session_id: str
    questions: List[Dict[str, Any]]


@app.post("/chat/questions")
async def add_questions(req: AddQuestionsRequest) -> Dict[str, Any]:
    """Add questions to a chat session."""
    if req.session_id not in _conversation_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    context = _conversation_sessions[req.session_id]
    
    for q_dict in req.questions:
        question = Question(**q_dict)
        question.asked_at = datetime.now().isoformat()
        context.questions.append(question)
    
    logger.info("Added %d questions to session %s", len(req.questions), req.session_id)
    return {"status": "ok", "questions_count": len(context.questions)}


class SubmitAnswerRequest(BaseModel):
    session_id: str
    question_id: str
    answer_text: str


@app.post("/chat/answer")
async def submit_answer(req: SubmitAnswerRequest) -> Dict[str, Any]:
    """Submit an answer to a question."""
    if req.session_id not in _conversation_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    context = _conversation_sessions[req.session_id]
    
    # Find question
    question = next((q for q in context.questions if q.question_id == req.question_id), None)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Create answer for the explicitly answered question
    answer = Answer(
        question_id=req.question_id,
        answer_text=req.answer_text,
        answered_at=datetime.now().isoformat(),
    )
    context.answers.append(answer)
    question.answered = True
    
    # Live-updating pipeline: infer which other open questions are now fully answered
    remaining_questions = [q for q in context.questions if not q.answered]
    auto_resolved_ids: list[str] = []
    if remaining_questions:
        try:
            auto_resolved_ids = infer_answered_questions_from_answer(
                answered_question=question,
                answer_text=req.answer_text,
                remaining_questions=remaining_questions,
            )
        except Exception as exc:
            logger.exception(
                "Failed to infer additionally answered questions for session %s: %s",
                req.session_id,
                exc,
            )
            auto_resolved_ids = []
    
    # Mark inferred questions as answered using the same answer text
    for qid in auto_resolved_ids:
        extra_q = next((q for q in context.questions if q.question_id == qid), None)
        if extra_q and not extra_q.answered:
            extra_answer = Answer(
                question_id=qid,
                answer_text=req.answer_text,
                answered_at=datetime.now().isoformat(),
            )
            context.answers.append(extra_answer)
            extra_q.answered = True
    
    if auto_resolved_ids:
        logger.info(
            "Answer to question %s in session %s also resolved %d other question(s): %s",
            req.question_id,
            req.session_id,
            len(auto_resolved_ids),
            auto_resolved_ids,
        )
    else:
        logger.info(
            "Answer submitted for question %s in session %s (no additional questions auto-resolved)",
            req.question_id,
            req.session_id,
        )
    
    return {
        "status": "ok",
        "answer": answer.model_dump(),
        "auto_resolved_question_ids": auto_resolved_ids,
    }


@app.get("/chat/session/{session_id}")
async def get_session(session_id: str) -> Dict[str, Any]:
    """Get conversation session details."""
    if session_id not in _conversation_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    context = _conversation_sessions[session_id]
    return {
        "session_id": context.session_id,
        "requirement_id": context.requirement_id,
        "questions": [q.model_dump() for q in context.questions],
        "answers": [a.model_dump() for a in context.answers],
        "created_at": context.created_at,
        "qa_context": context.get_qa_context(),
    }


@app.post("/enrich-build-query")
async def enrich_build_query_endpoint(req: EnrichBuildQueryRequest) -> Dict[str, Any]:
    """
    Enrich build query text with the latest Q&A context for a chat session.
    This keeps build_query.query_text as the single, fully populated source of truth.
    """
    from backend.models import BuildQuery

    try:
        build_query = BuildQuery(**req.build_query)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid build_query payload: {str(exc)}",
        ) from exc

    qa_context = ""
    if req.session_id and req.session_id in _conversation_sessions:
        context = _conversation_sessions[req.session_id]
        qa_context = context.get_qa_context()
        logger.info(
            "Enriching build query from session %s (answers=%d)",
            req.session_id,
            len(context.answers),
        )
    else:
        logger.info("Enrich build query called without valid session_id; using original build query text only")

    base_text = build_query.query_text or ""
    marker = "USER-PROVIDED INFORMATION (from Q&A):"
    idx = base_text.find(marker)
    if idx != -1:
        base_text = base_text[:idx].rstrip()

    if qa_context:
        enriched_text = f"{base_text.rstrip()}\n\n{qa_context}"
    else:
        enriched_text = base_text

    build_query.query_text = enriched_text
    return build_query.model_dump()


# Response preview and editing endpoints
_response_cache: Dict[str, List[Dict[str, Any]]] = {}


class PreviewResponseRequest(BaseModel):
    extraction: Dict[str, Any]
    requirements: Dict[str, Any]
    use_rag: bool = True
    num_retrieval_chunks: int = 5
    session_id: Optional[str] = None


@app.post("/preview-responses")
async def preview_responses_endpoint(req: PreviewResponseRequest) -> Dict[str, Any]:
    """Generate responses and return for preview (without PDF generation)."""
    logger.info("Preview responses endpoint called")
    try:
        from backend.models import ExtractionResult, RequirementsResult
        
        extraction_result = ExtractionResult(**req.extraction)
        requirements_result = RequirementsResult(**req.requirements)
        
        if not requirements_result.solution_requirements:
            raise HTTPException(
                status_code=400,
                detail="No solution requirements found. Cannot generate responses.",
            )
        
        # Check structure detection
        if requirements_result.structure_detection is None:
            structure_detection_dict = detect_structure(requirements_result.response_structure_requirements)
            requirements_result.structure_detection = StructureDetectionResult(**structure_detection_dict)
        
        structure_detection = requirements_result.structure_detection
        
        # For preview, we'll generate per-requirement responses (easier to edit)
        rag_system, knowledge_base = _setup_rag_and_kb(req.use_rag)
        
        # Get Q&A context
        qa_context = ""
        if req.session_id and req.session_id in _conversation_sessions:
            context = _conversation_sessions[req.session_id]
            qa_context = context.get_qa_context()
        
        # Validate
        validation_errors = validate_before_generation(extraction_result, requirements_result)
        if validation_errors:
            raise HTTPException(status_code=400, detail="Validation failed: " + "; ".join(validation_errors))
        
        individual_responses = []
        total_requirements = len(requirements_result.solution_requirements)
        
        for idx, solution_req in enumerate(requirements_result.solution_requirements, 1):
            try:
                build_query_obj = build_query_for_single_requirement(
                    extraction_result=extraction_result,
                    single_requirement=solution_req,
                    all_response_structure_requirements=requirements_result.response_structure_requirements,
                )
                build_query_obj.confirmed = True
                
                result = run_response_agent(
                    build_query=build_query_obj,
                    rag_system=rag_system,
                    num_retrieval_chunks=req.num_retrieval_chunks,
                    knowledge_base=knowledge_base,
                    qa_context=qa_context,
                )
                
                words = solution_req.normalized_text.split()
                key_phrase = " ".join(words[:10]) + ("..." if len(words) > 10 else "")
                
                # Assess response quality
                quality_assessment = assess_response_quality(solution_req, result.response_text)
                
                individual_responses.append({
                    "requirement_id": solution_req.id,
                    "requirement_text": solution_req.normalized_text,
                    "key_phrase": key_phrase,
                    "response": result.response_text,
                    "notes": result.notes,
                    "quality": quality_assessment,
                })
            except Exception as req_exc:
                logger.error("Failed to generate response for requirement %s: %s", solution_req.id, req_exc)
                words = solution_req.normalized_text.split()
                key_phrase = " ".join(words[:10]) + ("..." if len(words) > 10 else "")
                individual_responses.append({
                    "requirement_id": solution_req.id,
                    "requirement_text": solution_req.normalized_text,
                    "key_phrase": key_phrase,
                    "response": f"[ERROR: Failed to generate response: {str(req_exc)}]",
                    "notes": f"Error: {str(req_exc)}",
                    "quality": {
                        "score": 0.0,
                        "completeness": "incomplete",
                        "relevance": "low",
                        "issues": [f"Generation failed: {str(req_exc)}"],
                        "suggestions": ["Fix the error and regenerate"],
                    },
                })
        
        # Cache responses for editing
        preview_id = str(uuid.uuid4())
        _response_cache[preview_id] = individual_responses
        
        return {
            "preview_id": preview_id,
            "responses": individual_responses,
            "total": len(individual_responses),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Preview responses failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Preview generation failed: {str(exc)}",
        ) from exc


class UpdateResponseRequest(BaseModel):
    preview_id: str
    requirement_id: str
    response_text: str


@app.post("/update-response")
async def update_response_endpoint(req: UpdateResponseRequest) -> Dict[str, Any]:
    """Update a response in the preview cache."""
    if req.preview_id not in _response_cache:
        raise HTTPException(status_code=404, detail="Preview not found")
    
    responses = _response_cache[req.preview_id]
    response = next((r for r in responses if r["requirement_id"] == req.requirement_id), None)
    
    if not response:
        raise HTTPException(status_code=404, detail="Requirement not found in preview")
    
    response["response"] = req.response_text
    logger.info("Updated response for requirement %s in preview %s", req.requirement_id, req.preview_id)
    
    return {"status": "ok", "updated": True}


class GeneratePDFFromPreviewRequest(BaseModel):
    preview_id: str
    extraction: Dict[str, Any]
    requirements: Dict[str, Any]
    format: str = "pdf"  # pdf, docx, markdown


@app.post("/generate-pdf-from-preview")
async def generate_pdf_from_preview_endpoint(req: GeneratePDFFromPreviewRequest) -> Response:
    """Generate document from previewed (and possibly edited) responses. Supports PDF, DOCX, Markdown."""
    if req.preview_id not in _response_cache:
        raise HTTPException(status_code=404, detail="Preview not found")
    
    individual_responses = _response_cache[req.preview_id]
    
    extraction_result = ExtractionResult(**req.extraction)
    requirements_result = RequirementsResult(**req.requirements)
    
    rfp_title = f"RFP Response"
    if extraction_result.key_requirements_summary:
        rfp_title = f"RFP Response - {extraction_result.key_requirements_summary[:50]}..."
    
    project_root = Path(__file__).parent.parent
    timestamp = int(time.time())
    
    if req.format == "docx":
        from backend.document_formatter import generate_rfp_docx
        if not generate_rfp_docx:
            raise HTTPException(status_code=500, detail="DOCX generation not available. Install python-docx.")
        
        output_dir = project_root / "output" / "docx"
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"rfp_response_{extraction_result.language}_{timestamp}.docx"
        output_path = output_dir / filename
        
        docx_bytes = generate_rfp_docx(
            individual_responses=individual_responses,
            requirements_result=requirements_result,
            extraction_result=extraction_result,
            rfp_title=rfp_title,
            output_path=output_path,
        )
        
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(docx_bytes)),
            }
        )
    
    elif req.format == "markdown":
        from backend.document_formatter import generate_rfp_markdown
        
        output_dir = project_root / "output" / "markdown"
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"rfp_response_{extraction_result.language}_{timestamp}.md"
        output_path = output_dir / filename
        
        markdown_bytes = generate_rfp_markdown(
            individual_responses=individual_responses,
            requirements_result=requirements_result,
            extraction_result=extraction_result,
            rfp_title=rfp_title,
            output_path=output_path,
        )
        
        return Response(
            content=markdown_bytes,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(markdown_bytes)),
            }
        )
    
    else:  # Default to PDF
        from backend.document_formatter import generate_rfp_pdf
        
        output_dir = project_root / "output" / "pdfs"
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"rfp_response_{extraction_result.language}_{timestamp}.pdf"
        pdf_path = output_dir / filename
        
        pdf_bytes = generate_rfp_pdf(
            individual_responses=individual_responses,
            requirements_result=requirements_result,
            extraction_result=extraction_result,
            rfp_title=rfp_title,
            output_path=pdf_path,
        )
        
        pdf_bytes = pdf_path.read_bytes()
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(pdf_bytes)),
                "X-PDF-Path": str(pdf_path.absolute()),
            }
        )


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok"}


@app.get("/{path:path}")
async def serve_frontend(path: str):
    """
    Serve frontend routes (for SPA routing).
    This catches all non-API routes and serves the index.html.
    MUST be defined LAST so it doesn't interfere with API routes.
    
    Note: FastAPI matches more specific routes first, so API routes defined above
    will be matched before this catch-all. This route only serves the frontend
    for routes that don't match any API endpoint.
    """
    # Don't interfere with static assets - these are handled by StaticFiles mounts
    # If it's a static asset request, let it fall through to 404 (StaticFiles will handle it)
    if path.startswith(("assets/", "src/", "public/")):
        raise HTTPException(status_code=404, detail="Static file not found")
    
    # For all other routes, serve index.html (SPA routing)
    # FastAPI will have already matched API routes above, so this only catches frontend routes
    project_root = Path(__file__).resolve().parent.parent
    index_path = project_root / "frontend" / "dist" / "index.html"
    if not index_path.exists():
        index_path = project_root / "frontend" / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


