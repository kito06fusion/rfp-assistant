
from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import pickle

import faiss
import numpy as np
from dotenv import load_dotenv

from backend.llm.client import get_azure_client, REQUEST_TIMEOUT
from backend.pipeline.text_extraction import extract_text_from_file

logger = logging.getLogger(__name__)

load_dotenv()

EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSION = 3072

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

class RAGSystem:

    def __init__(self, docs_folder: str = "docs", index_path: Optional[str] = None, query_cache_path: Optional[str] = None):
        self.docs_folder = Path(docs_folder)
        self.index_path = Path(index_path) if index_path else None
        self.query_cache_path = Path(query_cache_path) if query_cache_path else None
        self.index: Optional[faiss.Index] = None
        self.metadata: List[Dict[str, Any]] = []
        self.client = None
        self._query_embedding_cache: Dict[str, np.ndarray] = {}
        self._load_query_cache()
        logger.info(
            "RAGSystem initialized (docs_folder=%s, index_path=%s, query_cache_size=%d)",
            self.docs_folder,
            self.index_path,
            len(self._query_embedding_cache),
        )

    def _get_query_hash(self, query: str) -> str:
        """Generate a hash for the query text to use as cache key."""
        return hashlib.sha256(query.encode('utf-8')).hexdigest()

    def _load_query_cache(self) -> None:
        """Load query embedding cache from disk if available."""
        if self.query_cache_path and self.query_cache_path.exists():
            try:
                with open(self.query_cache_path, "rb") as f:
                    cache_data = pickle.load(f)
                    self._query_embedding_cache = {
                        k: np.array(v, dtype=np.float32) 
                        for k, v in cache_data.items()
                    }
                logger.info(
                    "Loaded query embedding cache: %d entries from %s",
                    len(self._query_embedding_cache),
                    self.query_cache_path,
                )
            except Exception as e:
                logger.warning("Failed to load query cache: %s", e)
                self._query_embedding_cache = {}

    def _save_query_cache(self) -> None:
        """Save query embedding cache to disk."""
        if self.query_cache_path:
            try:
                self.query_cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_data = {
                    k: v.tolist() 
                    for k, v in self._query_embedding_cache.items()
                }
                with open(self.query_cache_path, "wb") as f:
                    pickle.dump(cache_data, f)
                logger.debug("Saved query embedding cache: %d entries", len(self._query_embedding_cache))
            except Exception as e:
                logger.warning("Failed to save query cache: %s", e)

    def _get_embedding_client(self):
        if self.client is None:
            embedding_api_key = os.environ.get("AZURE_OPENAI_EMBEDDING_API_KEY")
            embedding_endpoint = os.environ.get("AZURE_OPENAI_EMBEDDING_ENDPOINT")
            embedding_api_version = os.environ.get("AZURE_OPENAI_EMBEDDING_API_VERSION")
            
            if embedding_api_key and embedding_endpoint:
                logger.info("Using separate Azure OpenAI configuration for embeddings")
                from openai import AzureOpenAI
                self.client = AzureOpenAI(
                    api_key=embedding_api_key,
                    azure_endpoint=embedding_endpoint,
                    api_version=embedding_api_version or os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
                    timeout=REQUEST_TIMEOUT,
                )
            else:
                logger.info("Using main Azure OpenAI configuration for embeddings (no separate embedding config found)")
                self.client = get_azure_client()
        return self.client

    def _generate_embeddings(self, texts: List[str]) -> np.ndarray:
        client = self._get_embedding_client()
        embedding_deployment = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", EMBEDDING_MODEL)
        
        total_chars = sum(len(text) for text in texts)
        avg_text_length = total_chars / len(texts) if texts else 0
        
        logger.info(
            "Generating embeddings: %d texts, %d total chars, avg %d chars/text",
            len(texts),
            total_chars,
            int(avg_text_length),
        )

        start_time = time.time()
        try:
            logger.debug(
                "Requesting batch embeddings: %d texts, model=%s",
                len(texts),
                embedding_deployment,
            )
            response = client.embeddings.create(
                model=embedding_deployment,
                input=texts,
            )
            embeddings = [d.embedding for d in response.data]
            embeddings_array = np.array(embeddings, dtype=np.float32)
            elapsed = time.time() - start_time
            logger.info(
                "Embedding generation complete (batch): %d embeddings, dimension=%d, elapsed=%.2fs",
                len(embeddings),
                embeddings_array.shape[1] if len(embeddings) > 0 else 0,
                elapsed,
            )
            return embeddings_array
        except Exception:
            logger.exception("Batch embedding request failed, falling back to per-text embedding requests")

        embeddings = []
        start_time = time.time()
        for i, text in enumerate(texts):
            try:
                logger.debug("Generating embedding %d/%d: text_length=%d chars", i + 1, len(texts), len(text))
                response = client.embeddings.create(model=embedding_deployment, input=text)
                embedding = response.data[0].embedding
                embeddings.append(embedding)
            except Exception as e:
                logger.error(
                    "Failed to generate embedding for text %d (length: %d chars): %s",
                    i, len(text) if text else 0, str(e)
                )
                embeddings.append([0.0] * EMBEDDING_DIMENSION)

        elapsed = time.time() - start_time
        embeddings_array = np.array(embeddings, dtype=np.float32)
        logger.info(
            "Embedding generation complete (fallback): %d embeddings, dimension=%d, elapsed=%.2fs",
            len(embeddings),
            embeddings_array.shape[1] if len(embeddings) > 0 else 0,
            elapsed,
        )
        return embeddings_array

    def _chunk_text(self, text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
        text_length = len(text)
        logger.info("Chunking text: length=%d chars, chunk_size=%d, overlap=%d", text_length, chunk_size, overlap)
        
        if text_length <= chunk_size:
            logger.debug("Text is shorter than chunk_size, returning as single chunk")
            return [text]

        chunks = []
        start = 0
        chunk_num = 0
        
        while start < text_length:
            chunk_num += 1
            end = min(start + chunk_size, text_length)
            chunk = text[start:end]
            chunk_length = len(chunk)
            
            chunks.append(chunk)
            logger.debug(
                "Chunk %d: start=%d, end=%d, length=%d chars (%.1f%% of chunk_size)",
                chunk_num, start, end, chunk_length, (chunk_length / chunk_size * 100)
            )
            
            next_start = end - overlap
            if next_start <= start:
                logger.warning("Overlap is too large (%d), adjusting to prevent infinite loop", overlap)
                next_start = start + 1
            
            if next_start >= text_length:
                logger.debug("Reached end of text at position %d", next_start)
                break
                
            start = next_start
        
        logger.info(
            "Chunking complete: created %d chunks from %d chars (avg chunk size: %d chars, overlap: %d chars)",
            len(chunks), text_length, text_length // len(chunks) if chunks else 0, overlap
        )
        
        return chunks

    def _load_document(self, file_path: Path) -> str:
        suffix = file_path.suffix.lower()
        file_size = file_path.stat().st_size if file_path.exists() else 0
        logger.info(
            "Loading document: %s (type: %s, size: %d bytes)",
            file_path.name, suffix, file_size
        )

        try:
            if suffix == ".txt":
                text = file_path.read_text(encoding="utf-8")
                logger.info("Loaded TXT file: %d characters extracted", len(text))
                return text
            elif suffix in {".pdf", ".docx", ".doc"}:
                logger.debug("Extracting text from %s file using text extraction pipeline", suffix.upper())
                text = extract_text_from_file(file_path)
                logger.info("Extracted text from %s file: %d characters", suffix.upper(), len(text))
                return text
            else:
                raise ValueError(f"Unsupported file type: {suffix}")
        except Exception as e:
            logger.error("Failed to load document %s: %s", file_path, str(e))
            raise

    def build_index(self) -> None:
        if not self.docs_folder.exists():
            raise ValueError(f"Docs folder does not exist: {self.docs_folder}")

        logger.info("Building RAG index from documents in: %s", self.docs_folder)
        build_start_time = time.time()

        documents: List[Tuple[Path, str]] = []
        total_files_found = 0
        
        for ext in [".pdf", ".docx", ".doc", ".txt"]:
            files = list(self.docs_folder.glob(f"**/*{ext}"))
            total_files_found += len(files)
            logger.info("Found %d %s files", len(files), ext.upper())
            
            for file_path in files:
                try:
                    text = self._load_document(file_path)
                    if text.strip():
                        documents.append((file_path, text))
                        logger.info("Successfully loaded document: %s (%d chars)", file_path.name, len(text))
                    else:
                        logger.warning("Document %s is empty or contains only whitespace", file_path.name)
                except Exception as e:
                    logger.error("Failed to load document %s: %s", file_path, str(e), exc_info=True)
        
        logger.info(
            "Document loading complete: %d files found, %d successfully loaded",
            total_files_found, len(documents)
        )

        if not documents:
            raise ValueError(f"No documents found in {self.docs_folder}")

        logger.info("Starting chunking process for %d documents", len(documents))
        chunking_start_time = time.time()
        
        all_chunks: List[str] = []
        self.metadata = []

        for file_path, text in documents:
            logger.info("Processing document: %s (%d chars)", file_path.name, len(text))
            chunks = self._chunk_text(text)
            logger.info(
                "Document %s: created %d chunks (avg %d chars per chunk)",
                file_path.name, len(chunks), len(text) // len(chunks) if chunks else 0
            )
            
            for chunk_idx, chunk in enumerate(chunks):
                all_chunks.append(chunk)
                self.metadata.append({
                    "file_path": str(file_path),
                    "file_name": file_path.name,
                    "chunk_index": chunk_idx,
                    "total_chunks": len(chunks),
                    "chunk_text": chunk,
                })
                logger.debug(
                    "Added chunk %d/%d from %s (length: %d chars)",
                    chunk_idx + 1, len(chunks), file_path.name, len(chunk)
                )

        chunking_elapsed = time.time() - chunking_start_time
        logger.info(
            "Chunking complete: created %d chunks from %d documents in %.2fs (avg %.2f chunks/doc)",
            len(all_chunks), len(documents), chunking_elapsed,
            len(all_chunks) / len(documents) if documents else 0
        )

        embeddings = self._generate_embeddings(all_chunks)
        logger.info("Generated embeddings: shape %s", embeddings.shape)

        logger.info("Creating FAISS index...")
        index_start_time = time.time()
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(embeddings)
        index_elapsed = time.time() - index_start_time
        
        logger.info(
            "FAISS index created: %d vectors, dimension=%d, elapsed=%.2fs",
            self.index.ntotal, dimension, index_elapsed
        )
        
        total_elapsed = time.time() - build_start_time
        logger.info(
            "RAG index build complete: %d documents, %d chunks, %d vectors, total time=%.2fs",
            len(documents), len(all_chunks), self.index.ntotal, total_elapsed
        )

        if self.index_path:
            self.save_index()

    def save_index(self) -> None:
        if self.index_path is None:
            raise ValueError("index_path not set, cannot save index")

        if self.index is None:
            raise ValueError("No index to save. Call build_index() first.")

        logger.info("Saving index to: %s", self.index_path)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        faiss.write_index(self.index, str(self.index_path) + ".index")

        metadata_path = self.index_path.with_suffix(".metadata.pkl")
        with open(metadata_path, "wb") as f:
            pickle.dump(self.metadata, f)

        logger.info("Saved index and metadata")

    def load_index(self) -> None:
        if self.index_path is None:
            raise ValueError("index_path not set, cannot load index")

        index_file = Path(str(self.index_path) + ".index")
        metadata_file = self.index_path.with_suffix(".metadata.pkl")

        if not index_file.exists():
            raise FileNotFoundError(f"Index file not found: {index_file}")
        if not metadata_file.exists():
            raise FileNotFoundError(f"Metadata file not found: {metadata_file}")

        logger.info("RAG: Loading index from: %s", index_file)
        self.index = faiss.read_index(str(index_file))

        with open(metadata_file, "rb") as f:
            self.metadata = pickle.load(f)

        logger.info(
            "RAG: Loaded index with %d vectors and %d metadata entries (docs_folder=%s)",
            self.index.ntotal,
            len(self.metadata),
            self.docs_folder,
        )

    def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        if self.index is None:
            raise ValueError("Index not built. Call build_index() or load_index() first.")

        if not self.metadata:
            raise ValueError("Metadata not loaded. Call build_index() or load_index() first.")

        query_length = len(query)
        query_hash = self._get_query_hash(query)
        logger.info(
            "RAG search: query_length=%d chars, k=%d, index_size=%d vectors",
            query_length, k, self.index.ntotal
        )
        logger.debug("Query text (first 200 chars): %s", query[:200])

        embedding_start = time.time()
        if query_hash in self._query_embedding_cache:
            logger.debug("Query embedding cache HIT (hash=%s)", query_hash[:16])
            query_embedding = self._query_embedding_cache[query_hash]
            query_vector = query_embedding.reshape(1, -1).astype(np.float32)
            embedding_elapsed = time.time() - embedding_start
            logger.debug("Query embedding loaded from cache in %.2fs, dimension=%d", embedding_elapsed, query_vector.shape[1])
        else:
            logger.debug("Query embedding cache MISS (hash=%s) - generating new embedding", query_hash[:16])
            query_embedding = self._generate_embeddings([query])
            query_vector = query_embedding.reshape(1, -1).astype(np.float32)
            embedding_elapsed = time.time() - embedding_start
            self._query_embedding_cache[query_hash] = query_embedding[0]
            self._save_query_cache()
            logger.debug("Query embedding generated in %.2fs, dimension=%d (cached for future use)", embedding_elapsed, query_vector.shape[1])

        logger.debug("Searching FAISS index...")
        search_start = time.time()
        search_k = min(k, self.index.ntotal)
        distances, indices = self.index.search(query_vector, search_k)
        search_elapsed = time.time() - search_start
        logger.debug("FAISS search completed in %.2fs, found %d results", search_elapsed, len(indices[0]))

        results = []
        for i, (distance, idx) in enumerate(zip(distances[0], indices[0])):
            if idx < len(self.metadata):
                metadata = self.metadata[idx]
                chunk_text = metadata.get("chunk_text", "")
                result = {
                    "rank": i + 1,
                    "chunk_text": chunk_text,
                    "file_name": metadata.get("file_name", ""),
                    "file_path": metadata.get("file_path", ""),
                    "chunk_index": metadata.get("chunk_index", 0),
                    "distance": float(distance),
                }
                results.append(result)
                logger.debug(
                    "Result %d: file=%s, chunk=%d/%d, distance=%.4f, chunk_length=%d chars",
                    i + 1, result["file_name"], result["chunk_index"] + 1,
                    metadata.get("total_chunks", 0), distance, len(chunk_text)
                )
            else:
                logger.warning("Index %d out of bounds (metadata size: %d)", idx, len(self.metadata))

        total_elapsed = time.time() - embedding_start
        logger.info(
            "RAG search complete: %d results returned in %.2fs (embedding: %.2fs, search: %.2fs)",
            len(results), total_elapsed, embedding_elapsed, search_elapsed
        )
        
        if results:
            logger.debug(
                "Result distance range: min=%.4f, max=%.4f, avg=%.4f",
                min(r["distance"] for r in results),
                max(r["distance"] for r in results),
                sum(r["distance"] for r in results) / len(results)
            )
        
        return results

    def get_stats(self) -> Dict[str, Any]:
        stats = {
            "index_built": self.index is not None,
            "num_vectors": self.index.ntotal if self.index else 0,
            "num_metadata_entries": len(self.metadata),
            "embedding_dimension": EMBEDDING_DIMENSION,
            "embedding_model": EMBEDDING_MODEL,
        }

        if self.metadata:
            unique_files = set(m.get("file_name") for m in self.metadata)
            stats["num_documents"] = len(unique_files)

        return stats

