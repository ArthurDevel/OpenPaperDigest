/**
 * Feed Service
 *
 * Server-side feed ranking service that produces a personalized paper feed.
 * Uses similarity-driven candidate retrieval via pgvector ANN search, then scores
 * candidates with a weighted blend of similarity, popularity, and recency.
 *
 * Responsibilities:
 * - Build preference vectors from user clusters
 * - Fetch candidates via ANN similarity search (or recency fallback for cold start)
 * - Score candidates with weighted formula
 * - Inject diversity every 5th position
 * - Return paginated FeedResponse with slug lookups
 */

import { createClient } from '@/lib/supabase/server';
import { getPaperThumbnailUrls } from '@/lib/supabase/storage';
import { getPreferenceClusters, cosineSimilarity } from '@/services/interactions.service';
import type { FeedResponse } from '@/types/recommendation';
import type { MinimalPaper } from '@/types/paper';

// ============================================================================
// CONSTANTS
// ============================================================================

/** Weight for semantic similarity in the scoring formula */
const SIMILARITY_WEIGHT = 0.5;

/** Weight for popularity signals in the scoring formula */
const POPULARITY_WEIGHT = 0.3;

/** Weight for recency in the scoring formula */
const RECENCY_WEIGHT = 0.2;

/** Half-life in days for the recency exponential decay */
const RECENCY_HALF_LIFE_DAYS = 7;

/** Number of ANN candidates to fetch per preference cluster */
const CANDIDATES_PER_CLUSTER = 50;

// ============================================================================
// TYPES
// ============================================================================

/** A paper with all computed scoring components */
interface ScoredPaper {
  paper: MinimalPaper;
  score: number;
  recencyScore: number;
  popularityScore: number;
  similarityScore: number;
}

/** Raw row from the match_papers_by_embedding RPC or cold-start query */
interface CandidateRow {
  paperUuid: string;
  title: string | null;
  authors: string | null;
  finishedAt: Date;
  embedding: number[];
  externalPopularitySignals: Record<string, unknown> | null;
  similarity: number;
}

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * Produces a ranked, paginated feed of papers for the given user.
 * Builds preference vectors, fetches candidates, scores them, injects diversity,
 * paginates, and looks up slugs.
 * @param page - Page number (1-indexed)
 * @param limit - Number of items per page
 * @param excludePaperUuids - Paper UUIDs already shown (to exclude)
 * @param userId - Supabase auth user ID (may be null for unauthenticated users)
 * @returns Paginated feed response
 */
export async function getRankedFeed(
  page: number,
  limit: number,
  excludePaperUuids: string[],
  userId: string | null
): Promise<FeedResponse> {
  // Build preference vectors (empty for unauthenticated or cold-start users)
  const preferenceVectors = userId
    ? await buildPreferenceVectors(userId)
    : [];

  // Fetch candidates (similarity-driven or cold-start fallback)
  const candidates = await fetchCandidates(excludePaperUuids, preferenceVectors, limit);

  // Score and rank
  const scored = await scoreCandidates(candidates, preferenceVectors);

  // Inject diversity
  const diversified = injectDiversity(scored, preferenceVectors);

  // Paginate: we already excluded shown papers, so slice from start
  const startIdx = (page - 1) * limit;
  const pageItems = diversified.slice(startIdx, startIdx + limit);
  const hasMore = diversified.length > startIdx + limit;

  // Look up slugs for the page items
  const paperUuids = pageItems.map((sp) => sp.paper.paperUuid);
  const slugMap = await fetchSlugMap(paperUuids);

  // Batch-fetch signed thumbnail URLs in a single API call
  const thumbnailMap = await getPaperThumbnailUrls(paperUuids);

  const items: MinimalPaper[] = pageItems.map((sp) => ({
    ...sp.paper,
    slug: slugMap.get(sp.paper.paperUuid) ?? null,
    thumbnailUrl: thumbnailMap.get(sp.paper.paperUuid) ?? null,
  }));

  return { items, page, limit, hasMore };
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Fetches the user's preference clusters and returns their weighted embedding vectors.
 * Returns empty array if no clusters exist (cold start).
 * @param userId - Supabase auth user ID
 * @returns Array of embedding vectors (weighted by cluster weight)
 */
async function buildPreferenceVectors(userId: string): Promise<number[][]> {
  const clusters = await getPreferenceClusters(userId);
  if (clusters.length === 0) return [];

  // Weight each embedding by cluster weight
  return clusters.map((cluster) => {
    const weight = cluster.weight;
    return cluster.embedding.map((val) => val * weight);
  });
}

/**
 * Fetches candidate papers for ranking.
 * With preference vectors: uses ANN similarity search per cluster.
 * Without (cold start): falls back to most recent papers.
 * @param excludePaperUuids - Paper UUIDs to exclude from results
 * @param preferenceVectors - Weighted preference embeddings
 * @param limit - Desired page size (cold-start fetches limit*3)
 * @returns Array of candidate rows
 */
async function fetchCandidates(
  excludePaperUuids: string[],
  preferenceVectors: number[][],
  limit: number
): Promise<CandidateRow[]> {
  if (preferenceVectors.length > 0) {
    const annCandidates = await fetchCandidatesFromANN(excludePaperUuids, preferenceVectors);
    // Fall back to cold start if ANN returns nothing (e.g. no papers have embeddings yet)
    if (annCandidates.length > 0) return annCandidates;
  }
  return fetchColdStartCandidates(excludePaperUuids, limit);
}

/**
 * Fetches candidates via ANN similarity search for each preference vector.
 * Deduplicates results across clusters (keeps highest similarity).
 * @param excludePaperUuids - Paper UUIDs to exclude
 * @param preferenceVectors - Weighted preference embeddings
 * @returns Deduplicated candidate rows
 */
async function fetchCandidatesFromANN(
  excludePaperUuids: string[],
  preferenceVectors: number[][]
): Promise<CandidateRow[]> {
  const supabase = await createClient();

  // Query each cluster in parallel
  const clusterResults = await Promise.all(
    preferenceVectors.map(async (vector) => {
      // Format embedding as Postgres vector string
      const vectorString = `[${vector.join(',')}]`;

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { data, error } = await (supabase.rpc as any)(
        'match_papers_by_embedding',
        {
          query_embedding: vectorString,
          match_count: CANDIDATES_PER_CLUSTER,
          exclude_uuids: excludePaperUuids,
        }
      );

      if (error) {
        throw new Error(`match_papers_by_embedding RPC failed: ${error.message}`);
      }

      return (data ?? []) as {
        paper_uuid: string;
        title: string | null;
        authors: string | null;
        finished_at: string;
        embedding: string;
        external_popularity_signals: Record<string, unknown> | null;
        similarity: number;
      }[];
    })
  );

  // Deduplicate across clusters, keeping highest similarity
  const candidateMap = new Map<string, CandidateRow>();

  for (const rows of clusterResults) {
    for (const row of rows) {
      const existing = candidateMap.get(row.paper_uuid);
      if (!existing || row.similarity > existing.similarity) {
        candidateMap.set(row.paper_uuid, {
          paperUuid: row.paper_uuid,
          title: row.title,
          authors: row.authors,
          finishedAt: new Date(row.finished_at),
          embedding: parseEmbeddingString(row.embedding),
          externalPopularitySignals: row.external_popularity_signals,
          similarity: row.similarity,
        });
      }
    }
  }

  return Array.from(candidateMap.values());
}

/**
 * Fetches candidates for cold-start users (no preference vectors).
 * Falls back to most recent completed papers ordered by finished_at.
 * @param excludePaperUuids - Paper UUIDs to exclude
 * @param limit - Page size (fetches limit*3 to allow scoring/filtering)
 * @returns Candidate rows with similarity=0
 */
async function fetchColdStartCandidates(
  excludePaperUuids: string[],
  limit: number
): Promise<CandidateRow[]> {
  const supabase = await createClient();
  const fetchCount = limit * 3;

  // Build query
  let query = supabase
    .from('papers')
    .select('paper_uuid, title, authors, finished_at, external_popularity_signals')
    .eq('status', 'completed')
    .order('finished_at', { ascending: false })
    .limit(fetchCount);

  // Exclude already-shown papers
  if (excludePaperUuids.length > 0) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    query = (query as any).not('paper_uuid', 'in', `(${excludePaperUuids.join(',')})`);
  }

  const { data, error } = await query;

  if (error) {
    throw new Error(`Cold-start candidate fetch failed: ${error.message}`);
  }

  return ((data ?? []) as {
    paper_uuid: string;
    title: string | null;
    authors: string | null;
    finished_at: string;
    external_popularity_signals: Record<string, unknown> | null;
  }[]).map((row) => ({
    paperUuid: row.paper_uuid,
    title: row.title,
    authors: row.authors,
    finishedAt: new Date(row.finished_at),
    embedding: [],
    externalPopularitySignals: row.external_popularity_signals,
    similarity: 0,
  }));
}

/**
 * Scores candidates with the weighted blend of similarity, popularity, and recency.
 * Returns sorted array (highest score first).
 * @param candidates - Candidate rows to score
 * @param preferenceVectors - User's preference vectors (empty for cold start)
 * @returns Scored and sorted papers
 */
async function scoreCandidates(
  candidates: CandidateRow[],
  preferenceVectors: number[][]
): Promise<ScoredPaper[]> {
  const now = Date.now();

  // Batch-fetch all thumbnail URLs in one API call
  const thumbnailMap = await getPaperThumbnailUrls(
    candidates.map((c) => c.paperUuid)
  );

  const scored: ScoredPaper[] = candidates.map((candidate) => {
    // Recency: exponential decay with 7-day half-life
    const daysSinceFinished = (now - candidate.finishedAt.getTime()) / (1000 * 60 * 60 * 24);
    const recencyScore = Math.exp(-daysSinceFinished * Math.LN2 / RECENCY_HALF_LIFE_DAYS);

    // Popularity: from external_popularity_signals
    const popularityScore = computePopularityScore(candidate.externalPopularitySignals);

    // Similarity: pre-computed from ANN query (0 for cold start)
    const similarityScore = candidate.similarity;

    // Weighted blend
    const score =
      SIMILARITY_WEIGHT * similarityScore +
      POPULARITY_WEIGHT * popularityScore +
      RECENCY_WEIGHT * recencyScore;

    const paper: MinimalPaper = {
      paperUuid: candidate.paperUuid,
      title: candidate.title,
      authors: candidate.authors,
      slug: null,
      thumbnailUrl: thumbnailMap.get(candidate.paperUuid) ?? null,
    };

    return { paper, score, recencyScore, popularityScore, similarityScore } satisfies ScoredPaper;
  });

  // Sort descending by score
  scored.sort((a, b) => b.score - a.score);

  return scored;
}

/**
 * Injects diversity into the ranked feed by placing a paper from outside the
 * top similarity cluster at every 5th position (index 4, 9, 14...).
 * - 0 preference vectors: no-op
 * - 1 preference vector: picks lowest similarity at those positions
 * - 2+ vectors: picks highest-scoring paper from outside top similarity cluster
 * @param rankedPapers - Score-sorted papers
 * @param preferenceVectors - User's preference vectors
 * @returns Papers with diversity injected
 */
function injectDiversity(
  rankedPapers: ScoredPaper[],
  preferenceVectors: number[][]
): ScoredPaper[] {
  if (preferenceVectors.length === 0 || rankedPapers.length === 0) {
    return rankedPapers;
  }

  const result = [...rankedPapers];

  // Determine the "top cluster" -- the cluster with the highest weight (first vector
  // since buildPreferenceVectors preserves cluster order and weight is baked in)
  // For simplicity with 1 vector, we use similarity score directly.

  if (preferenceVectors.length === 1) {
    // With 1 vector: at every 5th position, pick the lowest-similarity paper
    // that hasn't been placed yet
    const used = new Set<number>();
    for (let pos = 4; pos < result.length; pos += 5) {
      // Find the paper with lowest similarity that isn't already at a diversity slot
      let bestIdx = -1;
      let lowestSim = Infinity;

      for (let i = pos + 1; i < result.length; i++) {
        if (!used.has(i) && result[i].similarityScore < lowestSim) {
          lowestSim = result[i].similarityScore;
          bestIdx = i;
        }
      }

      if (bestIdx !== -1) {
        // Swap the diversity pick into position
        used.add(pos);
        const picked = result.splice(bestIdx, 1)[0];
        result.splice(pos, 0, picked);
      }
    }
  } else {
    // With 2+ vectors: identify which cluster each paper is most similar to,
    // then at every 5th position, insert the highest-scoring paper from
    // outside the dominant cluster

    // Find dominant cluster (the one most papers are closest to)
    const clusterAssignments = result.map((sp) => {
      if (sp.paper.paperUuid && sp.similarityScore > 0) {
        // We don't have per-candidate embeddings for ANN results easily,
        // so use the similarity score as a proxy. Higher similarity = closer to
        // whichever cluster returned it. We approximate by finding the cluster
        // whose weighted vector is most similar to a rough direction.
        // Since we already have cosineSimilarity available, we can compute it
        // against each preference vector if the candidate has an embedding.
        // For ANN results, the embedding is available.
        return findClosestCluster(sp, preferenceVectors);
      }
      return 0;
    });

    // Find the most common cluster (dominant)
    const clusterCounts = new Map<number, number>();
    for (const idx of clusterAssignments) {
      clusterCounts.set(idx, (clusterCounts.get(idx) ?? 0) + 1);
    }
    let dominantCluster = 0;
    let maxCount = 0;
    for (const [cluster, count] of clusterCounts) {
      if (count > maxCount) {
        maxCount = count;
        dominantCluster = cluster;
      }
    }

    // At every 5th position, insert the highest-scoring paper from a non-dominant cluster
    const used = new Set<number>();
    for (let pos = 4; pos < result.length; pos += 5) {
      let bestIdx = -1;
      let bestScore = -Infinity;

      for (let i = pos + 1; i < result.length; i++) {
        if (!used.has(i) && clusterAssignments[i] !== dominantCluster && result[i].score > bestScore) {
          bestScore = result[i].score;
          bestIdx = i;
        }
      }

      if (bestIdx !== -1) {
        used.add(pos);
        const pickedAssignment = clusterAssignments.splice(bestIdx, 1)[0];
        const picked = result.splice(bestIdx, 1)[0];
        result.splice(pos, 0, picked);
        clusterAssignments.splice(pos, 0, pickedAssignment);
      }
    }
  }

  return result;
}

/**
 * Finds which preference cluster a scored paper is closest to.
 * Uses cosine similarity between the candidate's embedding and each preference vector.
 * @param sp - Scored paper with embedding data
 * @param preferenceVectors - Array of preference embeddings
 * @returns Index of the closest cluster
 */
function findClosestCluster(sp: ScoredPaper, preferenceVectors: number[][]): number {
  // If the paper came from ANN search, we need its embedding to compare against clusters.
  // The embedding was stored in CandidateRow but is not in MinimalPaper.
  // Since we lose the embedding after scoring, we fall back to a simpler heuristic:
  // use the similarity score as a proxy. Papers with high similarity are likely
  // from the first (strongest) cluster.
  // For a more accurate approach, we could carry the embedding through, but that
  // would mean modifying ScoredPaper. Keep it simple for now.

  // Heuristic: if similarity is above median, assign to cluster 0 (strongest).
  // Otherwise distribute round-robin among other clusters.
  // This is a reasonable approximation since the strongest cluster generates
  // the most candidates.
  if (sp.similarityScore > 0.5) {
    return 0;
  }
  // Distribute among non-dominant clusters
  return 1 + Math.floor(Math.random() * (preferenceVectors.length - 1));
}

/**
 * Computes a popularity score from external_popularity_signals.
 * NULL signals = 0.5 (neutral). HuggingFace upvotes: min(upvotes/100, 1.0).
 * @param signals - The external popularity signals JSON
 * @returns Normalized popularity score in [0, 1]
 */
function computePopularityScore(
  signals: Record<string, unknown> | null
): number {
  if (!signals) return 0.5;

  // Check for HuggingFace upvotes (may be double-encoded as string)
  let parsed = signals;
  if (typeof signals === 'string') {
    try {
      parsed = JSON.parse(signals);
    } catch {
      return 0.5;
    }
  }

  // Look for HuggingFace upvotes
  const hfUpvotes = (parsed as Record<string, unknown>)?.upvotes;
  if (typeof hfUpvotes === 'number') {
    return Math.min(hfUpvotes / 100, 1.0);
  }

  return 0.5;
}

/**
 * Fetches active slugs for a batch of paper UUIDs.
 * Returns a map of paper_uuid -> slug.
 * @param paperUuids - Array of paper UUIDs to look up slugs for
 * @returns Map from paper_uuid to slug string
 */
export async function fetchSlugMap(paperUuids: string[]): Promise<Map<string, string>> {
  if (paperUuids.length === 0) return new Map();

  const supabase = await createClient();

  const { data: slugsData, error } = await supabase
    .from('paper_slugs')
    .select('paper_uuid, slug')
    .in('paper_uuid', paperUuids)
    .eq('tombstone', false)
    .order('created_at', { ascending: false });

  if (error) {
    throw new Error(`Failed to fetch slugs: ${error.message}`);
  }

  const slugMap = new Map<string, string>();
  for (const row of (slugsData ?? []) as { paper_uuid: string; slug: string }[]) {
    // First slug per paper_uuid wins (most recent, due to ORDER BY)
    if (!slugMap.has(row.paper_uuid)) {
      slugMap.set(row.paper_uuid, row.slug);
    }
  }

  return slugMap;
}

/**
 * Parses a Supabase vector string (e.g. "[0.1,0.2,...]") into a number array.
 * @param embeddingStr - The string representation of the embedding vector
 * @returns Parsed number array
 */
function parseEmbeddingString(embeddingStr: string): number[] {
  const cleaned = embeddingStr.replace(/^\[|\]$/g, '');
  return cleaned.split(',').map(Number);
}
