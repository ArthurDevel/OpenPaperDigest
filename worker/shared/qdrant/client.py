from __future__ import annotations

from typing import List, Optional, Dict, Any
import logging

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchAny, MatchValue, Range

from shared.config import settings
from shared.qdrant.models import VectorPoint


# Domain-agnostic default; callers should pass an explicit collection
_COLLECTION_NAME = "vectors"

logger = logging.getLogger(__name__)


def _client() -> QdrantClient:
    return QdrantClient(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
        api_key=(settings.QDRANT_API_KEY or None),
        https=False,
    )


def ensure_collection(vector_size: int, collection: str = _COLLECTION_NAME) -> None:
    client = _client()
    existing = client.get_collections()
    names = {c.name for c in (existing.collections or [])}
    if collection in names:
        try:
            logger.info("Qdrant collection exists: name=%s size=%s (known)", collection, vector_size)
        except Exception:
            pass
        return
    client.recreate_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )
    try:
        logger.info("Qdrant collection created: name=%s size=%s distance=COSINE", collection, vector_size)
    except Exception:
        pass


def upsert_point(
    point_id: str,
    vector: List[float],
    payload: Dict[str, Any],
    collection: str = _COLLECTION_NAME,
) -> None:
    client = _client()
    point = PointStruct(
        id=point_id,
        vector=vector,
        payload={k: v for k, v in (payload or {}).items() if v is not None},
    )
    client.upsert(collection_name=collection, points=[point])
    try:
        logger.info(
            "Qdrant upsert: collection=%s id=%s vector_dim=%s payload_keys=%s",
            collection,
            str(point_id),
            len(vector) if isinstance(vector, list) else None,
            len((payload or {}).keys()),
        )
    except Exception:
        pass


def _build_filter(
    categories: Optional[List[str]] = None,
    date_from_ts: Optional[int] = None,
    date_to_ts: Optional[int] = None,
) -> Optional[Filter]:
    conditions: List[Any] = []
    if categories:
        conditions.append(
            FieldCondition(key="categories_array", match=MatchAny(any=categories))
        )
    if date_from_ts is not None:
        conditions.append(FieldCondition(key="published_epoch", range=Range(gte=date_from_ts)))
    if date_to_ts is not None:
        conditions.append(FieldCondition(key="published_epoch", range=Range(lte=date_to_ts)))
    if not conditions:
        return None
    return Filter(must=conditions)


def search_by_vector(
    query_vector: List[float],
    limit: int = 50,
    categories: Optional[List[str]] = None,
    date_from_ts: Optional[int] = None,
    date_to_ts: Optional[int] = None,
    collection: str = _COLLECTION_NAME,
) -> List[VectorPoint]:
    client = _client()
    flt = _build_filter(categories=categories, date_from_ts=date_from_ts, date_to_ts=date_to_ts)
    try:
        logger.info(
            "Qdrant search: collection=%s dim=%s limit=%s cats=%s date_from=%s date_to=%s filter=%s",
            collection,
            len(query_vector) if isinstance(query_vector, list) else None,
            limit,
            (categories or [])[:5],
            date_from_ts,
            date_to_ts,
            'yes' if flt else 'no',
        )
    except Exception:
        pass
    res = client.search(
        collection_name=collection,
        query_vector=query_vector,
        limit=max(1, limit),
        query_filter=flt,
        with_payload=True,
        with_vectors=False,
    )
    # Normalize into a generic list of dicts with payload and score
    out: List[VectorPoint] = []
    for p in res:
        out.append(VectorPoint(id=str(p.id), score=float(p.score) if p.score is not None else None, payload=p.payload or {}))
    try:
        logger.info("Qdrant search: hits=%s (collection=%s)", len(out), collection)
    except Exception:
        pass
    return out


def get_vector_by_id(point_id: str, collection: str = _COLLECTION_NAME) -> Optional[List[float]]:
    client = _client()
    recs = client.retrieve(collection_name=collection, ids=[point_id], with_vectors=True, with_payload=False)
    if not recs:
        try:
            logger.warning("Qdrant retrieve: not found id=%s collection=%s", str(point_id), collection)
        except Exception:
            pass
        return None
    vec = getattr(recs[0], "vector", None)
    out = list(vec) if isinstance(vec, list) else vec
    try:
        logger.info(
            "Qdrant retrieve: id=%s collection=%s dim=%s",
            str(point_id),
            collection,
            len(out) if isinstance(out, list) else None,
        )
    except Exception:
        pass
    return out


