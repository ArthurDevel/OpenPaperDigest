from __future__ import annotations

from typing import List, Optional, Dict, Any
import logging

import httpx

from shared.config import settings
from shared.voyageai.models import EmbeddingResult, RerankResult, RerankItem


"""
VoyageAI client helpers for embeddings and reranking.

- Embeddings: supports specifying input_type (query/document) and output_dimension (e.g., 2048)
- Reranking: ranks candidate documents against a query string
"""

_VOYAGE_BASE_URL = "https://api.voyageai.com/v1"
_HEADERS = {
    "Authorization": f"Bearer {settings.VOYAGE_API_KEY}",
    "Content-Type": "application/json",
}
_TIMEOUT_SECONDS = 60

logger = logging.getLogger(__name__)


def _get_async_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=_VOYAGE_BASE_URL, headers=_HEADERS, timeout=_TIMEOUT_SECONDS)


async def embed_texts(
    texts: List[str],
    model: str = "voyage-3.5",
    input_type: Optional[str] = "document",
    output_dimension: Optional[int] = None,
    truncation: bool = True,
) -> EmbeddingResult:
    """Get embeddings for a list of texts using VoyageAI.

    input_type: one of {"document", "query"} or None.
    output_dimension: one of {2048, 1024, 512, 256} for supported models.
    """
    if not isinstance(texts, list):
        raise TypeError("texts must be a list of strings")
    if not texts:
        return EmbeddingResult(vectors=[], model=model, dimensions=None, raw_response=None)

    payload: Dict[str, Any] = {
        "model": model,
        "input": texts,
        "input_type": input_type,
        "truncation": truncation,
    }
    if output_dimension is not None:
        payload["output_dimension"] = int(output_dimension)

    async with _get_async_client() as client:
        resp = await client.post("/embeddings", json=payload)
        resp.raise_for_status()
        data = resp.json()

    items = data.get("data") or []
    vectors: List[List[float]] = [it.get("embedding") for it in items if isinstance(it, dict)]
    indices: List[int] = [int(it.get("index")) for it in items if isinstance(it, dict) and it.get("index") is not None]
    dim: Optional[int] = len(vectors[0]) if vectors and isinstance(vectors[0], list) else None
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
    request_id = data.get("id") or data.get("request_id")
    try:
        logger.info(
            "Voyage embeddings: model=%s inputs=%d input_type=%s dim=%s request_id=%s",
            model,
            len(texts),
            input_type,
            dim,
            request_id,
        )
    except Exception:
        pass
    return EmbeddingResult(
        vectors=vectors,
        model=model,
        dimensions=dim,
        input_type=input_type,
        indices=indices or None,
        usage=usage,
        request_id=request_id,
        raw_response=data,
    )


async def embed_query(text: str, model: str = "voyage-3.5", output_dimension: Optional[int] = None) -> List[float]:
    """Convenience helper to embed a single query string."""
    res = await embed_texts([text], model=model, input_type="query", output_dimension=output_dimension)
    return res.vectors[0] if res.vectors else []


async def rerank(
    query: str,
    documents: List[str],
    top_k: int = 20,
    model: str = "rerank-2.5-lite",
) -> RerankResult:
    """Rerank candidate documents against a query using VoyageAI reranker."""
    if not documents:
        return RerankResult(model=model, items=[], raw_response=None)

    payload: Dict[str, Any] = {
        "model": model,
        "query": query,
        "documents": documents,
        "top_k": max(1, min(top_k, len(documents))),
    }
    async with _get_async_client() as client:
        resp = await client.post("/rerank", json=payload)
        resp.raise_for_status()
        data = resp.json()

    items_raw = data.get("data") or []
    items: List[RerankItem] = []
    for it in items_raw:
        try:
            idx = int(it.get("index"))
            # Voyage returns "relevance_score" (required)
            raw_score = it.get("relevance_score")
            score = float(raw_score)
            items.append(RerankItem(index=idx, score=score))
        except Exception:
            continue
    items.sort(key=lambda x: x.score, reverse=True)
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
    request_id = data.get("id") or data.get("request_id")
    try:
        top_preview = ", ".join([f"(i={it.index}, s={it.score:.4f})" for it in items[:5]])
        logger.info(
            "Voyage rerank: model=%s docs=%d top_k=%d returned=%d request_id=%s top=%s",
            model,
            len(documents),
            payload.get("top_k"),
            len(items),
            request_id,
            top_preview,
        )
    except Exception:
        pass
    return RerankResult(model=model, items=items, usage=usage, request_id=request_id, raw_response=data)


