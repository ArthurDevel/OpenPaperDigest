/**
 * Search Service
 *
 * Server-side semantic search using OpenRouter embeddings and pgvector.
 * Converts a user's text query into a vector embedding, then queries
 * the match_papers_by_embedding RPC for similar papers.
 */

import { createClient } from '@/lib/supabase/server';
import { getPaperThumbnailUrls } from '@/lib/supabase/storage';
import { fetchSlugMap } from '@/services/feed.service';
import type { MinimalPaper } from '@/types/paper';

// ============================================================================
// CONSTANTS
// ============================================================================

const OPENROUTER_API_KEY = process.env.OPENROUTER_API_KEY;
const OPENROUTER_EMBEDDINGS_URL = 'https://openrouter.ai/api/v1/embeddings';
const EMBEDDING_MODEL = 'openai/text-embedding-3-small';
const DEFAULT_MATCH_COUNT = 20;

/** Scoring weights (same as feed.service.ts) */
const SIMILARITY_WEIGHT = 0.5;
const POPULARITY_WEIGHT = 0.3;
const RECENCY_WEIGHT = 0.2;
const RECENCY_HALF_LIFE_DAYS = 7;

// ============================================================================
// MAIN
// ============================================================================

/**
 * Search papers by semantic similarity to a text query.
 * @param query - User's search text (topic description)
 * @param matchCount - Max results to return (default 20)
 * @returns Array of MinimalPaper sorted by similarity
 */
export async function searchPapers(
  query: string,
  matchCount: number = DEFAULT_MATCH_COUNT
): Promise<MinimalPaper[]> {
  const embedding = await generateQueryEmbedding(query);
  const vectorString = `[${embedding.join(',')}]`;

  const supabase = await createClient();

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data, error } = await (supabase.rpc as any)(
    'match_papers_by_embedding',
    {
      query_embedding: vectorString,
      match_count: matchCount,
      exclude_uuids: [],
    }
  );

  if (error) {
    throw new Error(`match_papers_by_embedding RPC failed: ${error.message}`);
  }

  const rows = (data ?? []) as {
    paper_uuid: string;
    title: string | null;
    authors: string | null;
    finished_at: string | null;
    external_popularity_signals: Record<string, unknown> | null;
    similarity: number;
  }[];

  if (rows.length === 0) return [];

  // Score with weighted blend of similarity, popularity, and recency
  const now = Date.now();
  const scored = rows.map((row) => {
    const recencyScore = row.finished_at
      ? Math.exp(-(now - new Date(row.finished_at).getTime()) / (1000 * 60 * 60 * 24) * Math.LN2 / RECENCY_HALF_LIFE_DAYS)
      : 0;
    const popularityScore = computePopularityScore(row.external_popularity_signals);
    const score =
      SIMILARITY_WEIGHT * row.similarity +
      POPULARITY_WEIGHT * popularityScore +
      RECENCY_WEIGHT * recencyScore;
    return { row, score };
  });

  scored.sort((a, b) => b.score - a.score);

  const paperUuids = scored.map((s) => s.row.paper_uuid);
  const [slugMap, thumbnailMap] = await Promise.all([
    fetchSlugMap(paperUuids),
    getPaperThumbnailUrls(paperUuids),
  ]);

  return scored.map(({ row }) => ({
    paperUuid: row.paper_uuid,
    title: row.title,
    authors: row.authors,
    slug: slugMap.get(row.paper_uuid) ?? null,
    thumbnailUrl: thumbnailMap.get(row.paper_uuid) ?? null,
  }));
}

// ============================================================================
// HELPERS
// ============================================================================

/**
 * Computes a popularity score from external_popularity_signals.
 * Same logic as feed.service.ts.
 */
function computePopularityScore(
  signals: Record<string, unknown> | null
): number {
  if (!signals) return 0.5;

  let parsed = signals;
  if (typeof signals === 'string') {
    try {
      parsed = JSON.parse(signals);
    } catch {
      return 0.5;
    }
  }

  const hfUpvotes = (parsed as Record<string, unknown>)?.upvotes;
  if (typeof hfUpvotes === 'number') {
    return Math.min(hfUpvotes / 100, 1.0);
  }

  return 0.5;
}

/**
 * Generate a 1536-dim embedding for a text query via OpenRouter.
 */
async function generateQueryEmbedding(text: string): Promise<number[]> {
  if (!OPENROUTER_API_KEY) {
    throw new Error('OPENROUTER_API_KEY is not set');
  }

  const response = await fetch(OPENROUTER_EMBEDDINGS_URL, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${OPENROUTER_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: EMBEDDING_MODEL,
      input: text,
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`OpenRouter embeddings API error (${response.status}): ${body}`);
  }

  const result = await response.json();
  return result.data[0].embedding as number[];
}
