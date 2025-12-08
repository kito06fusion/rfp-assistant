RFP Assistant – Backend Pipeline

## Overview

This workspace contains a backend pipeline that:
- **Accepts an RFP / tender as PDF or DOCX**.
- **Extracts raw text** from the document.
- Sends the text through **three LLM agents**:
  - **Extraction agent** (Azure OpenAI `gpt-5-chat`)  
    - Detects language, translates to English, extracts CPV and other codes, identifiers, etc.  
  - **Scope agent** (Azure OpenAI `gpt-5-chat`)  
    - Removes unnecessary information (addresses, boilerplate, etc.), returns essential text + what was removed.  
  - **Requirements agent** (Azure OpenAI `gpt-5-chat`)  
    - Splits content into **solution requirements** and **response-structure requirements**.
- **Vision OCR fallback** (HuggingFace `Qwen/Qwen2.5-VL-7B-Instruct`)
  - Used when direct text extraction fails for scanned/image-based documents.

The main orchestrator is `backend/pipeline/rfp_pipeline.py`, and the HTTP API entrypoint is `backend/app.py`.

## Running the backend

1. **Install dependencies** (ideally in a virtual environment):

```bash
pip install -r requirements.txt
```

2. **Set environment variables**:

Create a `.env` file or export the following variables:

```bash
# Azure OpenAI Configuration (required for main agents)
export AZURE_OPENAI_API_KEY="your_azure_openai_api_key_here"
export AZURE_OPENAI_ENDPOINT="https://your-resource-name.openai.azure.com"
export AZURE_OPENAI_API_VERSION="2024-02-15-preview"  # Optional, defaults to this
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5-chat"  # Optional, defaults to "gpt-5-chat"

# HuggingFace Configuration (required for vision OCR fallback)
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
