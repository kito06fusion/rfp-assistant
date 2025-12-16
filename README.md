# RFP Response Assistant

An AI-powered system for processing Request for Proposals (RFPs) and generating comprehensive response documents. The system uses a multi-agent pipeline to extract, analyze, and respond to RFP requirements.

## Test Documents

Test documents can be found in the `test_documents/` folder:

- **`Global Contractor Agencies RFP - Nov 2025.docx`** - An RFP document that does **not** have a required response structure. The system will generate responses per individual requirement.
- **`MTI_BPM_Tender_Example_from_RFP.pdf`** - An RFP document that **does** have a required response structure. The system will detect this structure and generate a structured response following the specified format.

## Complete Pipeline Sequence

The RFP Assistant processes documents through the following sequence from user upload to final output:

### 1. Document Upload

- User uploads an RFP document (supports PDF, DOCX, DOC, XLSX, XLS, TXT)

### 2. Text Extraction (OCR)

- **Direct Extraction**: Attempts to extract text directly using:
  - `pdfplumber` for PDFs
  - `python-docx` for DOCX files
  - `pandas` for Excel files
  - Direct file reading for TXT files
- **Vision OCR Fallback**: If direct extraction fails or returns insufficient text (e.g., scanned documents), the system:
  - Converts the document to images (PDF → images, DOCX → PDF → images)
  - Uses the Qwen2.5-VL-7B-Instruct vision model to extract text from each page
  - Combines all extracted text with page break markers

### 3. Extraction Agent

- Analyzes the extracted text to identify:
  - Document language
  - CPV codes (Common Procurement Vocabulary), code used in Europe to define rfp goal and requirements
  - Other classification codes
  - Key requirements summary
  - Metadata and document structure

### 4. Scope Agent

- Analyzes the full text to distinguish:
  - **Essential text**: Content relevant to solution requirements and response structure
  - **Removed text**: Boilerplate, legal disclaimers, and non-essential content
- Provides rationale for what was kept vs. removed
- Has a comparison agent within to check whether removed information does not contain essential text
- User can review and manually edit the scoped text before proceeding

### 5. Requirements Agent

- Processes the essential text to extract:
  - **Solution Requirements**: Specific requirements that need to be addressed in the response
  - **Response Structure Requirements**: Instructions on how the response should be formatted/structured
- Each requirement is categorized and normalized
- **Structure Detection**: Automatically detects if the RFP specifies an explicit response structure:
  - If structure is detected with high confidence (≥0.6), the system will use structured response generation
  - Otherwise, it generates responses per individual requirement

### 6. Build Query

- Consolidates all requirements and extraction data into a comprehensive query
- Includes:
  - Summary of solution requirements
  - Response structure requirements (if any)
  - Context from extraction (language, codes, key requirements)
- User can review and confirm the build query before generating responses

### 7. Q&A Chat Session

- **Step 1: RAG Information Retrieval**

  - The system first uses RAG (Retrieval-Augmented Generation) to search the document library for relevant information related to each requirement
  - RAG retrieves relevant chunks from prior RFP responses and knowledge documents
  - This identifies what information is **already available** in the knowledge base
- **Step 2: Question Generation**

  - Based on the RAG retrieval results, the system generates questions for information that is **missing or unclear**
  - Questions focus on gaps where:
    - Information is not found in RAG results
    - Details are ambiguous or need clarification
    - Company-specific information is required
  - The system avoids generating questions for information already found in RAG context
- **Step 3: User Answers**

  - Users provide answers to the generated questions
  - Answers are incorporated into the response generation context
  - This enriches responses with specific company information, clarifications, and details not available in the knowledge base

### 8. Response Generation

The system uses one of two approaches based on structure detection:

#### A. Structured Response (when explicit structure detected)

- Generates a single, comprehensive response following the detected structure
- Organizes content according to the specified sections/format
- Uses the `structured_response_agent` to create a cohesive document

#### B. Per-Requirement Response (default)

- Generates individual responses for each solution requirement
- For each requirement:
  - Builds a focused query for that specific requirement
  - Uses the `response_agent` with:
    - Knowledge base (company capabilities, case studies, accelerators)
    - RAG system (if enabled) to retrieve relevant context from document library
    - Q&A context (if chat session was used)
  - Assesses response quality (completeness, relevance, etc.)
- Combines all individual responses into a single document

### 9. Output Generation

- Generates a formatted Word document (DOCX) containing:
  - Document title and metadata
  - Response structure requirements (if any)
  - All solution requirement responses
  - Quality assessments and notes
- Document is saved to `output/docx/` directory
- User can download the document directly from the frontend

## Architecture

- **Backend**: FastAPI (Python) with multiple specialized agents
- **Frontend**: React with Vite
- **LLM**: Azure OpenAI (configurable model)
- **RAG System**: FAISS-based vector search for document retrieval
- **Knowledge Base**: Company capabilities, case studies, and accelerators

## Setup

See `docker-compose.yml` for deployment configuration. The system requires:

- Azure OpenAI API credentials
- Optional: HuggingFace token for vision model OCR
- Python dependencies (see `requirements.txt`)
- Node.js dependencies (see `package.json`)

# Output Location

Generated documents are saved to:

- `output/docx/` - Word documents
- `output/pdfs/` - PDF files (if generated)
- `output/markdown/` - Markdown files (if generated)

# How to use

Start up docker:

- ```
  docker compose up -d --build
  ```
- Visit UI on localhost:8000
