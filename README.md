RFP Assistant – Backend Pipeline

## Overview

This workspace contains a backend pipeline that:
- **Accepts an RFP / tender as PDF or DOCX**.
- **Extracts raw text** from the document.
- Sends the text through **three LLM agents via the Hugging Face router**:
  - **Extraction agent** (`meta-llama/Llama-3.2-1B-Instruct:novita`)  
    - Detects language, translates to English, extracts CPV and other codes, identifiers, deadlines, budget, etc.  
  - **Scope agent** (`google/gemma-2-2b-it:nebius`)  
    - Removes unnecessary information (addresses, boilerplate, etc.), returns essential text + what was removed.  
  - **Requirements agent** (`meta-llama/Llama-3.1-8B-Instruct:novita`)  
    - Splits content into **solution requirements** and **response-structure requirements**.

The main orchestrator is `backend/pipeline/rfp_pipeline.py`, and the HTTP API entrypoint is `backend/app.py`.

## Running the backend

1. **Install dependencies** (ideally in a virtual environment):

```bash
pip install -r requirements.txt
```

2. **Set the Hugging Face router token**:

```bash
export HF_TOKEN="your_huggingface_token_here"
```

3. **Run the FastAPI app**:

```bash
uvicorn backend.app:app --reload --port 8000
```

4. **Call the RFP processing endpoint**:

- URL: `POST http://localhost:8000/process-rfp`
- Body: `multipart/form-data` with field `file` (PDF or DOCX).

The response JSON includes:
- `extraction`: translated text, language, CPV codes, other codes, key requirement summary, and metadata.
- `scope`: essential text, removed text, rationale, merged structured info.
- `requirements`: structured lists of `solution_requirements` and `response_structure_requirements`.

There is also a simple health check at `GET /health`.
