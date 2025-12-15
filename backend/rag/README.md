# RAG System Documentation

This module provides a Retrieval-Augmented Generation (RAG) system using FAISS and Azure OpenAI embeddings.

## Features

- **Document Loading**: Supports PDF, DOCX, and TXT files from a `docs` folder
- **Text Chunking**: Splits documents into overlapping chunks for better retrieval
- **Embeddings**: Uses Azure OpenAI `text-embedding-3-large` (3072 dimensions)
- **Vector Store**: FAISS for fast similarity search
- **Persistence**: Save and load indexes for reuse

## Setup

1. **Install dependencies** (already in requirements.txt):
   ```bash
   pip install faiss-cpu numpy
   ```

2. **Set environment variables** (in addition to existing Azure OpenAI vars):
   ```bash
   # Required (same as for chat models)
   AZURE_OPENAI_API_KEY=your_key
   AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
   AZURE_OPENAI_API_VERSION=2024-02-15-preview
   
   # Optional: If your embedding deployment has a different name
   AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME=text-embedding-3-large
   ```

3. **Create a docs folder** with your documents:
   ```
   docs/
     ├── document1.pdf
     ├── document2.docx
     └── subfolder/
         └── document3.txt
   ```

## Usage

### Basic Example

```python
from backend.rag import RAGSystem

# Initialize RAG system
rag = RAGSystem(docs_folder="docs", index_path="rag_index")

# Build index from documents
rag.build_index()

# Search for similar documents
results = rag.search("What are the security requirements?", k=5)

for result in results:
    print(f"Rank {result['rank']}: {result['file_name']}")
    print(f"Distance: {result['distance']}")
    print(f"Text: {result['chunk_text'][:200]}...")
    print()
```

### Save and Load Index

```python
# After building, save the index
rag.save_index()

# Later, load the existing index (much faster than rebuilding)
rag.load_index()
```

### Get Statistics

```python
stats = rag.get_stats()
print(f"Index built: {stats['index_built']}")
print(f"Number of vectors: {stats['num_vectors']}")
print(f"Number of documents: {stats['num_documents']}")
```

## Configuration

You can adjust chunking parameters in `rag_system.py`:

```python
CHUNK_SIZE = 1000      # Characters per chunk
CHUNK_OVERLAP = 200    # Overlap between chunks
```

## File Structure

```
backend/rag/
├── __init__.py           # Module exports
├── rag_system.py         # Main RAG system implementation
├── example_usage.py      # Example script
└── README.md            # This file
```

## API Reference

### `RAGSystem(docs_folder, index_path=None)`

Initialize the RAG system.

- `docs_folder`: Path to folder containing documents
- `index_path`: Optional path to save/load FAISS index

### `build_index()`

Build FAISS index from all documents in the docs folder. This will:
1. Load all PDF, DOCX, and TXT files
2. Split them into chunks
3. Generate embeddings
4. Create FAISS index

### `save_index()`

Save the FAISS index and metadata to disk. Creates two files:
- `{index_path}.index` - FAISS index
- `{index_path}.metadata.pkl` - Metadata (file paths, chunk info)

### `load_index()`

Load previously saved index and metadata from disk.

### `search(query, k=5)`

Search for similar documents.

- `query`: Search query text
- `k`: Number of results to return

Returns list of dictionaries with:
- `rank`: Result rank (1-based)
- `chunk_text`: Full text of the chunk
- `file_name`: Name of source file
- `file_path`: Full path to source file
- `chunk_index`: Index of chunk in document
- `distance`: L2 distance (lower = more similar)

### `get_stats()`

Get statistics about the RAG system.

Returns dictionary with:
- `index_built`: Whether index exists
- `num_vectors`: Number of vectors in index
- `num_metadata_entries`: Number of metadata entries
- `num_documents`: Number of unique documents
- `embedding_dimension`: Embedding dimension (3072)
- `embedding_model`: Model name

## Running the Example

```bash
python -m backend.rag.example_usage
```

Make sure you have:
1. Created a `docs` folder with some documents
2. Set the required environment variables
3. Installed all dependencies

