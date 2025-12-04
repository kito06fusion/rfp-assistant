from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from backend.pipeline.text_extraction import extract_text_from_file
from backend.agents.extraction_agent import run_extraction_agent
from backend.agents.scope_agent import run_scope_agent
from backend.agents.requirements_agent import run_requirements_agent


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


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    index_path = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.post("/process-rfp")
async def process_rfp(file: UploadFile = File(...)) -> Dict[str, Any]:
    request_id = str(uuid.uuid4())
    logger.info("REQUEST %s: /process-rfp file=%s", request_id, file.filename)

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".pdf", ".docx", ".doc"}:
        logger.warning("REQUEST %s: unsupported file type %s", request_id, suffix)
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Please upload a PDF or DOCX/DOC file.",
        )

    temp_path = Path("/tmp") / f"{request_id}_{file.filename}"
    content = await file.read()
    temp_path.write_bytes(content)
    logger.info(
        "REQUEST %s: wrote temp file %s (%d bytes)",
        request_id,
        temp_path,
        len(content),
    )

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
        "REQUEST %s: scope agent finished (removed_chars=%d, cleaned_chars=%d)",
        request_id,
        len(scope_res.removed_text or ""),
        len(scope_res.cleaned_text or ""),
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


@app.post("/run-requirements")
async def run_requirements(req: RequirementsRequest) -> Dict[str, Any]:
    logger.info(
        "Requirements endpoint called (essential_chars=%d)", len(req.essential_text)
    )
    try:
        result = run_requirements_agent(essential_text=req.essential_text, structured_info={})
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


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok"}


