## Complete Pipeline Sequence

The RFP Assistant processes documents through the following sequence from user upload to final output:

### 1. Document Upload

- User uploads one or more RFP documents (supports PDF, DOCX, DOC, XLSX, XLS, TXT).
- The **Upload** section shows basic file info and triggers the backend pipeline.

### 2. Text Extraction (OCR)

- **Direct Extraction**: Attempts to extract text directly using:
  - `pdfplumber` for PDFs
  - `python-docx` for DOCX files
  - `pandas` for Excel files
  - Direct file reading for TXT files
- **Vision OCR Fallback**: If direct extraction fails or returns insufficient text (e.g., scanned PDFs):
  - Converts the document to images (PDF → images, DOCX → PDF → images)
  - Uses the **Qwen2.5‑VL‑7B‑Instruct** vision model to extract text from each page
  - Combines all extracted text with page break markers
- The resulting raw text is shown in the **“1. OCR (Qwen)”** tab, where you can *edit the OCR text* before running the next step.

### 3. Preprocess Agent

- Runs a single LLM‑based preprocessing step (`gpt-5-chat` on Azure OpenAI) over the full OCR text to:
  - Detect **document language**
  - Extract **CPV codes** and other classification metadata
  - Produce a **key requirements summary**
  - Split the text into:
    - **Cleaned text** (essential content kept for downstream steps)
    - **Removed text** (boilerplate, legal, non‑essential content)
- Includes an internal **comparison check** to confirm that nothing essential was removed.
- In the frontend:
  - The OCR text can be edited before you click **“Confirm & Run Preprocess”**.
  - The **“2. Preprocess Agent”** tab shows a formatted view of the result and lets you toggle an editable JSON view for advanced tweaks.
  - Confirming preprocess automatically kicks off the Requirements Agent.

### 4. Requirements Agent

- Processes the **cleaned text** from preprocess to extract:
  - **Solution Requirements**: specific requirements that must be addressed in the response
  - **Response Structure Requirements**: instructions on how the response should be formatted/structured
- Each requirement is categorized and normalized.
- **Structure Detection**:
  - Automatically detects if the RFP specifies an explicit response structure.
  - If structure is detected with confidence ≥ 0.6:
    - The system can generate a single, structured response document.
  - Otherwise:
    - It falls back to per‑requirement responses.
- The **“3. Requirements”** tab shows a human‑readable summary and an optional JSON editor so you can adjust requirements before continuing.

### 5. Build Query

- Consolidates all requirements and preprocess metadata into a single **build query** object.
- Includes:
  - Summary of solution requirements
  - Summary of response‑structure requirements
  - Context from preprocess (language, codes, key requirements)
- The **“4. Build Query”** tab:
  - Displays the full build‑query text
  - Lets you edit the text in place via a simple editor
  - Allows you to **confirm** the build query once you are happy
- When you confirm the build query, the system:
  - Starts an **iterative Q&A flow** (see below)
  - Requires all critical questions to be answered before you can generate the final response

### 6. Q&A Chat Session (Iterative Critical Questions)

The Q&A flow runs in the right‑hand **Interactive Q&A** panel, independent from the main tabs.

- The backend keeps a **conversation session** with:
  - All generated questions
  - All user answers
  - A compact Q&A context string used during response generation

The flow works as follows:

1. **Iterative question generation**

   - After the build query is confirmed, the backend uses:
     - The requirements
     - The build query
     - (Optionally) RAG context from your documents
   - It generates **one critical question at a time** for missing or ambiguous information.
   - The UI shows the current question plus a running history of previous Q&A.
2. **User answers**

   - You answer each question in the chat panel.
   - You can also **Skip** a question; skipped questions are still recorded as “[Skipped]”.
   - After each answer, the backend:
     - Updates the conversation context
     - Optionally enriches the build query internally
3. **Completion**

   - Once no more questions are needed, the Q&A panel shows **“All critical questions answered”**.
   - Only when all questions are answered (or explicitly skipped) can you confirm the build query and move on to response generation.
   - The Q&A context is injected into the response‑generation step so the final document reflects your answers.

### 7. Response Generation

The system uses one of two approaches based on structure detection in the requirements:

#### A. Structured Response (when explicit structure detected)

- Generates a single, comprehensive response following the detected structure.
- Organizes content according to the specified sections/format.
- Uses the `structured_response_agent` to create a cohesive, document‑level answer.

#### B. Per‑Requirement Response (default path)

- Generates individual responses for each **solution requirement**.
- For each requirement:
  - Builds a focused build‑query for that single requirement.
  - Invokes the `response_agent` with:
    - The company knowledge base (capabilities, case studies, accelerators)
    - The **RAG system** (if enabled) to retrieve relevant context from your `docs/` library
    - The **Q&A conversation context** gathered in the chat panel
  - Runs a **quality assessment** to score completeness and relevance and track issues/suggestions.
- All per‑requirement responses are then combined into one final document.

The **“5. Response”** tab shows a textual indication that the DOCX/PDF was generated successfully (and its size) rather than an inline preview.

### 8. Output Generation

- Generates a formatted **Word document (DOCX)** for both structured and per‑requirement modes.
- Depending on the path:
  - For structured responses, the full RFP answer is written to a single DOCX file.
  - For per‑requirement responses, each requirement’s answer is assembled into the final document.
- Output location on disk:
  - `output/docx/` — generated Word documents
  - `output/pdfs/` — generated PDFs (when PDF generation is used)
  - `output/markdown/` — generated Markdown files (when markdown export is used)
- The frontend automatically triggers a download when you generate a response; you can also find the file in the `output/` directory if running locally.

## Architecture

- **Backend**: FastAPI (Python) with multiple specialized agents:
  - Text extraction pipeline
  - Preprocess agent
  - Requirements agent + structure detection
  - Per‑requirement response agent
  - Structured response agent
  - Question‑generation and Q&A session handling
- **Frontend**: React + Vite, with:
  - Upload section
  - Pipeline progress tracker
  - Agent tabs (`OCR`, `Preprocess`, `Requirements`, `Build Query`, `Response`)
  - Fixed chat sidebar for the Q&A flow
- **LLM**: **Azure OpenAI** via `AzureOpenAI` (no direct OpenAI usage):
  - `gpt-5-chat` (or your configured deployment) for all text‑only agents
- **RAG System**: FAISS‑based vector search over documents in the `docs/` folder.
- **Knowledge Base**: Hand‑crafted company knowledge (capabilities, case studies, accelerators) loaded from `backend/knowledge_base`.
- **Local Memory Store**: Lightweight JSONL store at `backend/memory/data/memories.jsonl` that records anonymized snapshots of:
  - Preprocess results
  - Requirements extraction
  - Build‑query metadata
    This file is **ignored by git** and stays on the local machine or backend container only.

  Quick local retrieval example

  - The backend includes a simple local search API in `backend/memory/mem0_client.py`:
    - `search_memories(query: str, max_results: int = 5, stage: Optional[str] = None)`
    - It loads `backend/memory/data/memories.jsonl` and returns the top matching records using a small token-overlap score.
  - Usage (from Python agent code):

    ```py
    from backend.memory.mem0_client import search_memories

    matches = search_memories("unclear requirement about hosting", max_results=3, stage="requirements")
    for m in matches:
        # m contains the original record plus `score` and `snippet`
        print(m["score"], m["snippet"])
    ```

  - Suggested integration: when an LLM or agent indicates low understanding for a requirement, call `search_memories()` and inject the `snippet` or full `messages` into the prompt as extra context before re-asking the model.

## Setup

See `docker-compose.yml` for deployment configuration. The system requires:

- **Azure OpenAI**:
  - `AZURE_OPENAI_API_KEY`
  - `AZURE_OPENAI_ENDPOINT`
  - (Optional) `AZURE_OPENAI_API_VERSION` and `AZURE_OPENAI_DEPLOYMENT_NAME`
- **Optional vision OCR**:
  - `HF_TOKEN` for HuggingFace (used by the Qwen vision model)
- **Python dependencies**: see `requirements.txt`
- **Node.js dependencies**: see `package.json`

# Output Location

Generated documents are saved to:

- `output/docx/` — Word documents
- `output/pdfs/` — PDF files (if generated)
- `output/markdown/` — Markdown files (if generated)

# How to use

Start up Docker:

docker compose up -d --buildThen open the UI at `http://localhost:8000` and work through the tabs:

1. Upload your RFP.
2. Review/edit OCR text and run **Preprocess**.
3. Inspect and, if needed, edit **Requirements**.
4. Build and confirm the **Build Query**, then answer any critical questions in the chat panel.
5. Generate the final DOCX/PDF from the **Response** tab and download it.
