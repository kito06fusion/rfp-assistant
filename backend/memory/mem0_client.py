from __future__ import annotations

import hashlib
import json
import logging
import re
import os
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STORE_PATH = DATA_DIR / "memories.jsonl"
EMBED_CACHE_PATH = DATA_DIR / "embeddings.jsonl"

RETRIEVAL_METHOD = os.environ.get("MEM0_RETRIEVAL_METHOD", "token").lower()
_default_embedding = os.environ.get("MEM0_EMBEDDING_MODEL")
if not _default_embedding:
    try:
        from backend.rag.rag_system import EMBEDDING_MODEL as _RAG_EMBEDDING
        _default_embedding = _RAG_EMBEDDING
    except Exception:
        _default_embedding = "text-embedding-3-small"
EMBEDDING_MODEL = os.environ.get("MEM0_EMBEDDING_MODEL", _default_embedding)

#function to append a memory record to the local JSONL store
def _append_record(record: Dict[str, Any]) -> bool:
    try:
        with STORE_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception as exc:
        logger.warning("Failed to write local memory record: %s", exc)
        return False

#function to build stored messages for a preprocess payload
def _build_messages(preprocess_payload: Dict[str, Any]) -> list[Dict[str, str]]:
    summary = preprocess_payload.get("key_requirements_summary") or "RFP preprocess summary"
    cleaned_text = preprocess_payload.get("cleaned_text") or ""
    truncated_cleaned = cleaned_text[:4000]

    payload_snapshot = {
        "key_requirements_summary": summary,
        "language": preprocess_payload.get("language"),
        "removed_text_length": len(preprocess_payload.get("removed_text") or ""),
        "cleaned_text_excerpt": truncated_cleaned,
    }

    return [
        {"role": "user", "content": summary},
        {"role": "assistant", "content": json.dumps(payload_snapshot)},
    ]

#function to build stored messages for a requirements payload
def _build_requirements_messages(requirements_payload: Dict[str, Any]) -> list[Dict[str, str]]:
    sol = requirements_payload.get("solution_requirements") or []
    resp = requirements_payload.get("response_structure_requirements") or []
    notes = requirements_payload.get("notes") or ""

    def _simplify(reqs: Any, max_items: int = 100) -> list[Dict[str, str]]:
        items: list[Dict[str, str]] = []
        if not isinstance(reqs, list):
            return items
        for raw in reqs[:max_items]:
            if not isinstance(raw, dict):
                continue
            text = str(raw.get("source_text") or "")
            items.append(
                {
                    "id": str(raw.get("id") or ""),
                    "type": str(raw.get("type") or ""),
                    "category": str(raw.get("category") or ""),
                    "source_text": text[:2000],
                }
            )
        return items

    snapshot = {
        "summary": "RFP requirements snapshot",
        "solution_requirements_count": len(sol) if isinstance(sol, list) else 0,
        "response_structure_requirements_count": len(resp) if isinstance(resp, list) else 0,
        "solution_requirements": _simplify(sol),
        "response_structure_requirements": _simplify(resp),
        "notes": str(notes),
    }

    return [
        {"role": "user", "content": "RFP REQUIREMENTS SNAPSHOT"},
        {"role": "assistant", "content": json.dumps(snapshot)},
    ]

#function to build stored messages for a build-query payload
def _build_build_query_messages(build_query_payload: Dict[str, Any]) -> list[Dict[str, str]]:
    query_text = str(build_query_payload.get("query_text") or "")
    sol_summary = str(build_query_payload.get("solution_requirements_summary") or "")
    resp_summary = str(build_query_payload.get("response_structure_requirements_summary") or "")

    snapshot = {
        "summary": "RFP build query snapshot",
        "solution_requirements_summary": sol_summary[:4000],
        "response_structure_requirements_summary": resp_summary[:4000],
        "query_preview": query_text[:8000],
    }

    return [
        {"role": "user", "content": "RFP BUILD QUERY SNAPSHOT"},
        {"role": "assistant", "content": json.dumps(snapshot)},
    ]

#function to store preprocess results into local memory
def store_preprocess_result(source_text: str, preprocess_payload: Dict[str, Any]) -> bool:
    if not source_text:
        logger.debug("Mem0: no OCR text supplied; skipping preprocess storage")
        return False

    try:
        user_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    except Exception as exc:
        logger.warning("Failed to hash OCR text for Mem0 storage: %s", exc)
        return False

    metadata = {
        "stage": "preprocess",
        "language": preprocess_payload.get("language"),
        "source": "rfp-assistant",
    }

    messages = _build_messages(preprocess_payload)

    record: Dict[str, Any] = {
        "user_id": user_hash,
        "stage": metadata["stage"],
        "metadata": metadata,
        "messages": messages,
    }
    ok = _append_record(record)
    if ok:
        logger.info("Mem0: stored preprocess record for user_id=%s at %s", user_hash[:12], STORE_PATH)
    else:
        logger.warning("Mem0: failed to store preprocess record for user_id=%s", user_hash[:12])
    return ok

#function to store extracted requirements into local memory
def store_requirements_result(source_text: str, requirements_payload: Dict[str, Any]) -> bool:
    if not source_text:
        logger.debug("Mem0: no essential text supplied; skipping requirements storage")
        return False

    try:
        user_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    except Exception as exc:
        logger.warning("Failed to hash essential text for Mem0 requirements storage: %s", exc)
        return False

    metadata = {
        "stage": "requirements",
        "source": "rfp-assistant",
    }

    messages = _build_requirements_messages(requirements_payload)

    record: Dict[str, Any] = {
        "user_id": user_hash,
        "stage": metadata["stage"],
        "metadata": metadata,
        "messages": messages,
    }
    ok = _append_record(record)
    if ok:
        logger.info("Mem0: stored requirements record for user_id=%s at %s", user_hash[:12], STORE_PATH)
    else:
        logger.warning("Mem0: failed to store requirements record for user_id=%s", user_hash[:12])
    return ok

#function to store build-query payload into local memory
def store_build_query_result(source_text: str, build_query_payload: Dict[str, Any]) -> bool:
    if not source_text:
        logger.debug("Mem0: no essential text supplied; skipping build-query storage")
        return False

    try:
        user_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    except Exception as exc:
        logger.warning("Failed to hash essential text for Mem0 build query storage: %s", exc)
        return False

    metadata = {
        "stage": "build_query",
        "source": "rfp-assistant",
    }

    messages = _build_build_query_messages(build_query_payload)

    record: Dict[str, Any] = {
        "user_id": user_hash,
        "stage": metadata["stage"],
        "metadata": metadata,
        "messages": messages,
    }
    ok = _append_record(record)
    if ok:
        logger.info("Mem0: stored build-query record for user_id=%s at %s", user_hash[:12], STORE_PATH)
    else:
        logger.warning("Mem0: failed to store build-query record for user_id=%s", user_hash[:12])
    return ok

#function to tokenize text into lowercase word tokens
def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return re.findall(r"\w+", text.lower())

#function to search local memory records for a text query
def search_memories(query: str, max_results: int = 5, stage: Optional[str] = None) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if not query or not STORE_PATH.exists():
        logger.debug("Mem0 search skipped: empty query or missing store (exists=%s)", STORE_PATH.exists())
        return results

    q_tokens = _tokenize(query)
    if not q_tokens:
        logger.debug("Mem0 search: query tokenization produced no tokens: %r", query)
        return results

    logger.info("Mem0 search starting: method=%s query_len=%d stage=%s max_results=%d", RETRIEVAL_METHOD, len(query), stage, max_results)

    try:
        with STORE_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    continue

                if stage and record.get("stage") != stage:
                    continue

                parts: List[str] = []
                for m in record.get("messages", []) or []:
                    parts.append(str(m.get("content") or ""))
                meta = record.get("metadata") or {}
                for v in meta.values():
                    parts.append(str(v))
                doc_text = " ".join(parts).strip().lower()
                if not doc_text:
                    continue

                doc_tokens = _tokenize(doc_text)
                if not doc_tokens:
                    continue

                if RETRIEVAL_METHOD == "embeddings":
                    out = dict(record)
                    out["_doc_text"] = doc_text
                    results.append(out)
                else:
                    score = 0
                    for qt in q_tokens:
                        occ = doc_tokens.count(qt)
                        if occ:
                            score += occ

                    denom = max(1, len(doc_tokens))
                    normalized = score / denom
                    if normalized <= 0:
                        continue

                    snippet = ""
                    first_pos = None
                    for i, t in enumerate(doc_tokens):
                        if t in q_tokens:
                            first_pos = i
                            break
                    if first_pos is not None:
                        start = max(0, first_pos - 8)
                        end = min(len(doc_tokens), first_pos + 24)
                        snippet = " ".join(doc_tokens[start:end])

                    out = dict(record)
                    out["score"] = normalized
                    out["snippet"] = snippet
                    results.append(out)

    except Exception as exc:
        logger.warning("Failed to read/search memories file: %s", exc)
        return []

    if RETRIEVAL_METHOD == "embeddings" and results:
        try:
            q_emb = _get_embedding(query)
            logger.info("Mem0: computed query embedding (len=%d)", len(q_emb) if q_emb else 0)
            if not q_emb:
                raise RuntimeError("Failed to compute query embedding")
            scored: List[Dict[str, Any]] = []
            for rec in results:
                doc_text = rec.get("_doc_text") or ""
                doc_emb = _embedding_for_record_cached(rec, doc_text)
                logger.debug("Mem0: candidate doc fingerprint present: %s, emb_len=%d", rec.get("user_id") or "<no-user>", len(doc_emb) if doc_emb else 0)
                if not doc_emb:
                    continue
                sim = _cosine_similarity(q_emb, doc_emb)
                if sim and sim > 0:
                    out = dict(rec)
                    out.pop("_doc_text", None)
                    out["score"] = sim
                    tokens = _tokenize(doc_text)
                    out["snippet"] = " ".join(tokens[:60])
                    scored.append(out)
            scored.sort(key=lambda r: r.get("score", 0), reverse=True)
            logger.info("Mem0 embeddings retrieval: %d candidates scored, returning top %d", len(scored), min(max_results, len(scored)))
            return scored[:max_results]
        except Exception as e:
            logger.warning("Embeddings retrieval failed, falling back to token matches: %s", e)

    results.sort(key=lambda r: r.get("score", 0), reverse=True)
    logger.info("Mem0 token retrieval: %d matches found, returning top %d", len(results), min(max_results, len(results)))
    for r in results[:min(5, len(results))]:
        try:
            logger.debug("Mem0 match: user_id=%s score=%.4f snippet=%s", (r.get("user_id") or "<no-user>")[:12], r.get("score", 0.0), (r.get("snippet") or "")[:200])
        except Exception:
            pass
    return results[:max_results]

#function to compute cosine similarity between two vectors
def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    num = sum(x * y for x, y in zip(a, b))
    denom = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if denom == 0:
        return 0.0
    return num / denom

#function to compute an embedding for text using HF or Azure clients
def _get_embedding(text: str) -> List[float]:
    from backend.llm.client import get_hf_client, get_azure_client

    if not text:
        return []

    try:
        if os.environ.get("HF_TOKEN"):
            client = get_hf_client()
            logger.debug("Mem0 embedding: using HF client, model=%s", EMBEDDING_MODEL)
            resp = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
            emb = resp.data[0].embedding
            logger.debug("Mem0 embedding: HF response length=%d", len(emb) if emb else 0)
            return list(emb)
        elif os.environ.get("AZURE_OPENAI_API_KEY"):
            client = get_azure_client()
            logger.debug("Mem0 embedding: using Azure client, model=%s", EMBEDDING_MODEL)
            resp = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
            emb = resp.data[0].embedding
            logger.debug("Mem0 embedding: Azure response length=%d", len(emb) if emb else 0)
            return list(emb)
    except Exception as e:
        logger.warning("Failed to compute embedding: %s", e)
        return []
    logger.debug("No embedding client available for mem0 (HF_TOKEN / AZURE_OPENAI_API_KEY missing)")
    return []

#function to compute a deterministic fingerprint for a memory record
def _record_fingerprint(record: Dict[str, Any]) -> str:
    s = json.dumps(record.get("messages") or [] , sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

#function to return cached embedding for a record, computing and caching if missing
def _embedding_for_record_cached(record: Dict[str, Any], doc_text: str) -> List[float]:
    fp = _record_fingerprint(record)
    cache: Dict[str, List[float]] = {}
    try:
        if EMBED_CACHE_PATH.exists():
            with EMBED_CACHE_PATH.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        o = json.loads(line)
                        if o.get("fp") and o.get("embedding"):
                            cache[o["fp"]] = o["embedding"]
                    except Exception:
                        continue
    except Exception:
        cache = {}

    if fp in cache:
        return cache[fp]

    emb = _get_embedding(doc_text)
    if not emb:
        return []

    try:
        with EMBED_CACHE_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"fp": fp, "embedding": emb, "ts": int(time.time())}, ensure_ascii=False) + "\n")
    except Exception:
        pass

    return emb
