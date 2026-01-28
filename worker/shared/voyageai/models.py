from __future__ import annotations

from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class EmbeddingResult(BaseModel):
    """Result of an embeddings call.

    - vectors: One vector per input text in the same order
    - model: The embedding model used
    - dimensions: Optional dimension of the vectors (if known)
    - raw_response: Optional raw provider response for debugging/usage tracking
    """

    vectors: List[List[float]]
    model: str
    dimensions: Optional[int] = None
    # Additional metadata to keep the client general-purpose
    input_type: Optional[str] = None
    indices: Optional[List[int]] = None
    usage: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


class RerankItem(BaseModel):
    """Represents a single reranked document reference.

    - index: Index of the document in the input list
    - score: Relevance score (higher is more relevant)
    """

    index: int
    score: float


class RerankResult(BaseModel):
    """Result of a rerank call containing items sorted by descending score."""

    model: str
    items: List[RerankItem]
    # Additional metadata to keep the client general-purpose
    usage: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


