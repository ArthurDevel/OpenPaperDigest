from __future__ import annotations

import logging
from typing import Optional, Tuple, List, Union, Dict, Any
from datetime import datetime

from shared.qdrant.client import (
    search_by_vector as qdrant_search_by_vector,
    get_vector_by_id as qdrant_get_vector_by_id,
    ensure_collection as qdrant_ensure_collection,
)
from shared.voyageai.client import embed_query as voyage_embed_query, rerank as voyage_rerank
from shared.openrouter.client import get_json_response as or_get_json_response, get_llm_response as or_get_llm_response
from search.internals.prompt_loader import load_prompt as load_arxiv_prompt
from shared.utils import to_epoch_seconds
from shared.arxiv.client import _read_arxiv_categories


logger = logging.getLogger(__name__)


_to_epoch_seconds = to_epoch_seconds


async def search_by_user_query(
    query: str,
    is_new: bool = False,
    selected_categories: Optional[List[str]] = None,
    date_from: Optional[Union[str, datetime]] = None,
    date_to: Optional[Union[str, datetime]] = None,
    limit: int = 20,
    rerank_top_k: int = 50,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Orchestrate user search across VoyageAI + Qdrant with optional LLM-assisted filters.
    Returns (results, meta).
    results: list of { point, qdrant_score, rerank_score }
    meta: { rewritten_query?, applied_categories?, applied_date_from?, applied_date_to? }
    """
    original_query = (query or '').strip()
    if not original_query:
        return [], {"error": "empty_query"}

    applied_categories: Optional[List[str]] = selected_categories[:] if selected_categories else None
    applied_date_from = date_from
    applied_date_to = date_to
    rewritten_query: Optional[str] = None

    # Step A: Always ask LLM for a rewritten query (even when filters are provided)
    # (frontend no longer provides an is_new toggle)
    if True:
        try:
            cats = _read_arxiv_categories()
            # Load prompts
            rewrite_sys = load_arxiv_prompt('search_rewrite_system.md')
            # cats_sys = load_arxiv_prompt('search_select_categories_system.md')
            # dates_sys = load_arxiv_prompt('search_select_dates_system.md')

            # Run three calls in parallel
            import asyncio
            rewrite_task = asyncio.create_task(or_get_llm_response([
                {"role": "system", "content": rewrite_sys},
                {"role": "user", "content": original_query},
            ], model="openai/gpt-oss-120b"))
            # cats_input = f"Query: {original_query}\n\nValid categories (examples): {', '.join(cats[:100])} ..."
            # cats_task = asyncio.create_task(or_get_json_response(system_prompt=cats_sys, user_prompt=cats_input, model="openai/gpt-oss-120b"))
            # dates_input = f"Query: {original_query}"
            # dates_task = asyncio.create_task(or_get_json_response(system_prompt=dates_sys, user_prompt=dates_input, model="openai/gpt-oss-120b"))

            # rewrite_res, cats_res, dates_res = await asyncio.gather(rewrite_task, cats_task, dates_task, return_exceptions=True)
            rewrite_res = await rewrite_task

            # Handle rewrite result
            if not isinstance(rewrite_res, Exception):
                text = (rewrite_res.response_text or '').strip() if rewrite_res else ''
                if text:
                    rewritten_query = text

            # # Handle categories JSON (bypassed for now)
            # if not isinstance(cats_res, Exception):
            #     data_c = getattr(cats_res, 'parsed_json', None) or {}
            #     if isinstance(data_c.get('selected_categories'), list) and data_c['selected_categories']:
            #         applied_categories = [str(x) for x in data_c['selected_categories'] if isinstance(x, (str, int))]
            #     try:
            #         logger.info(
            #             "LLM categories output: generation_id=%s raw_len=%s parsed=%s applied=%s",
            #             getattr(cats_res, 'generation_id', None),
            #             len((getattr(cats_res, 'response_text', None) or '')),
            #             data_c,
            #             applied_categories,
            #         )
            #     except Exception:
            #         pass
            # else:
            #     try:
            #         logger.exception("LLM categories selection failed with exception: %s", cats_res)
            #     except Exception:
            #         pass

            # # Handle dates JSON (bypassed for now)
            # if not isinstance(dates_res, Exception):
            #     data_d = getattr(dates_res, 'parsed_json', None) or {}
            #     df = data_d.get('date_from')
            #     dt = data_d.get('date_to')
            #     if applied_date_from is None and isinstance(df, str):
            #         applied_date_from = df
            #     if applied_date_to is None and isinstance(dt, str):
            #         applied_date_to = dt
            #     try:
            #         logger.info(
            #             "LLM dates output: generation_id=%s raw_len=%s parsed=%s applied_from=%s applied_to=%s",
            #             getattr(dates_res, 'generation_id', None),
            #             len((getattr(dates_res, 'response_text', None) or '')),
            #             data_d,
            #             applied_date_from,
            #             applied_date_to,
            #         )
            #     except Exception:
            #         pass
            # else:
            #     try:
            #         logger.exception("LLM dates selection failed with exception: %s", dates_res)
            #     except Exception:
            #         pass

            try:
                logger.info(
                    "User search LLM parallel: rewritten=%s cats=%s dates=%s→%s",
                    bool(rewritten_query),
                    (applied_categories or [])[:5],
                    applied_date_from,
                    applied_date_to,
                )
            except Exception:
                pass
        except Exception:
            logger.exception("Parallel LLM selection failed; proceeding without it")

    # Step B: Embed query via Voyage
    query_text = (rewritten_query or original_query)
    # Ensure query embedding matches the collection dimension
    try:
        logger.info("Embedding query text len=%s rewritten=%s", len(query_text), bool(rewritten_query))
    except Exception:
        pass
    query_vector = await voyage_embed_query(query_text, output_dimension=2048)
    if not query_vector:
        return [], {"error": "embed_failed"}

    # Step C: Qdrant vector search with filters
    date_from_ts = _to_epoch_seconds(applied_date_from)
    date_to_ts = _to_epoch_seconds(applied_date_to)
    initial_k = max(limit, min(rerank_top_k, 200))
    # Ensure collection exists (domain-owned): arxiv_papers, 2048-dim, cosine distance
    try:
        qdrant_ensure_collection(vector_size=2048, collection="arxiv_papers")
    except Exception:
        logger.exception("Failed to ensure Qdrant collection arxiv_papers")
    raw_hits = qdrant_search_by_vector(
        query_vector=query_vector,
        limit=initial_k,
        categories=applied_categories,
        date_from_ts=date_from_ts,
        date_to_ts=date_to_ts,
        collection="arxiv_papers",
    )
    try:
        logger.info(
            "Qdrant returned hits=%s for query (limit=%s, rerank_top_k=%s) cats=%s",
            len(raw_hits),
            limit,
            rerank_top_k,
            (applied_categories or [])[:5],
        )
    except Exception:
        pass

    if not raw_hits:
        return [], {"rewritten_query": rewritten_query, "applied_categories": applied_categories, "applied_date_from": applied_date_from, "applied_date_to": applied_date_to}

    # Step D: Rerank candidates strictly using summary text only
    documents: List[str] = []
    doc_to_hit_index: List[int] = []
    for idx, h in enumerate(raw_hits):
        payload = h.payload or {}
        summary = payload.get('summary')
        if isinstance(summary, str):
            summary = summary.strip()
        if summary:
            documents.append(summary)
            doc_to_hit_index.append(idx)
    try:
        logger.info("Documents prepared for rerank=%s (from hits=%s)", len(documents), len(raw_hits))
    except Exception:
        pass

    # If no summaries available, return empty result (no guessing / no fallback)
    if not documents:
        logger.error("Rerank skipped: no summaries available in Qdrant payloads (documents=0)")
        return [], {
            "rewritten_query": rewritten_query,
            "applied_categories": applied_categories,
            "applied_date_from": applied_date_from,
            "applied_date_to": applied_date_to,
        }

    try:
        top_k = min(limit, len(documents))
        rr = await voyage_rerank(query=query_text, documents=documents, top_k=top_k)
        order = rr.items or []
        try:
            logger.info(
                "Rerank result: items=%s top_preview=%s",
                len(order),
                ", ".join([f"(i={it.index}, s={it.score:.4f})" for it in order[:5]]),
            )
        except Exception:
            pass
        out: List[Dict[str, Any]] = []
        if order:
            # Build results in rerank order
            for item in order:
                doc_idx = item.index
                if 0 <= doc_idx < len(doc_to_hit_index):
                    hit_idx = doc_to_hit_index[doc_idx]
                    hit = raw_hits[hit_idx]
                    entry = {
                        "point": {"id": hit.id, "payload": hit.payload},
                        "qdrant_score": hit.score,
                        "rerank_score": item.score,
                    }
                    try:
                        logger.info(
                            "Rerank mapped: id=%s qdrant=%.6f rerank=%.6f",
                            str(hit.id),
                            (hit.score or 0.0),
                            (item.score or 0.0),
                        )
                    except Exception:
                        pass
                    out.append(entry)
                else:
                    try:
                        logger.warning("Rerank index out of range: doc_idx=%s docs=%s", doc_idx, len(doc_to_hit_index))
                    except Exception:
                        pass
        else:
            # Reranker returned nothing; log and fall back to Qdrant order
            logger.error("Reranker returned no items; falling back to Qdrant order (hits=%s, docs=%s)", len(raw_hits), len(documents))
            out = [
                {"point": {"id": h.id, "payload": h.payload}, "qdrant_score": h.score, "rerank_score": None}
                for h in raw_hits[:limit]
            ]
        try:
            logger.info("Returning results: count=%s (limited to %s)", len(out[:limit]), limit)
        except Exception:
            pass
        return out[:limit], {
            "rewritten_query": rewritten_query,
            "applied_categories": applied_categories,
            "applied_date_from": applied_date_from,
            "applied_date_to": applied_date_to,
        }
    except Exception:
        logger.exception("Rerank failed; falling back to Qdrant order")
        out_fb: List[Dict[str, Any]] = [
            {"point": {"id": h.id, "payload": h.payload}, "qdrant_score": h.score, "rerank_score": None}
            for h in raw_hits[:limit]
        ]
        try:
            logger.info("Returning fallback results: count=%s (limited to %s)", len(out_fb), limit)
        except Exception:
            pass
        return out_fb, {
            "rewritten_query": rewritten_query,
            "applied_categories": applied_categories,
            "applied_date_from": applied_date_from,
            "applied_date_to": applied_date_to,
        }


async def find_similar_papers(
    paper_uuid: str,
    limit: int = 20,
    categories: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Find similar papers by vector only (no date filters, no reranking).
    Excludes the focal paper from results.
    Returns list of { point, qdrant_score } in Qdrant order.
    """
    if not paper_uuid:
        return []
    vec = qdrant_get_vector_by_id(paper_uuid)
    if not vec:
        try:
            logger.warning("Similar papers: vector not found for id=%s", str(paper_uuid))
        except Exception:
            pass
        return []
    # Ensure collection exists before searching
    try:
        qdrant_ensure_collection(vector_size=2048, collection="arxiv_papers")
    except Exception:
        logger.exception("Failed to ensure Qdrant collection arxiv_papers")
    hits = qdrant_search_by_vector(query_vector=vec, limit=max(1, limit + 1), categories=categories, collection="arxiv_papers")
    try:
        logger.info("Similar papers: initial hits=%s (requested limit=%s)", len(hits), limit)
    except Exception:
        pass
    out: List[Dict[str, Any]] = []
    for h in hits:
        if str(h.id) == str(paper_uuid):
            continue
        out.append({"point": {"id": h.id, "payload": h.payload}, "qdrant_score": h.score})
        if len(out) >= limit:
            break
    try:
        logger.info("Similar papers: returning=%s", len(out))
    except Exception:
        pass
    return out


