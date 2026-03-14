/**
 * Feed Service
 *
 * Server-side feed ranking service that produces a personalized paper feed.
 * Uses similarity-driven candidate retrieval via pgvector ANN search, combined
 * with an exploration pool for topic discovery. Scores candidates with a weighted
 * blend of similarity, author popularity, recency, and HuggingFace upvotes.
 *
 * Responsibilities:
 * - Build preference vectors from user clusters (raw embeddings, normalized weights)
 * - Fetch candidates via ANN similarity search + exploration pool
 * - Score candidates: 0.33 * similarity + 0.33 * authorPopularity + 0.33 * recency + 0.33 * hfUpvotes (capped at 1.0)
 * - Inject diversity (cluster balancing + exploration interleaving)
 * - Return paginated FeedResponse with slug lookups
 */

import { createClient } from '@/lib/supabase/server';
import { getPaperThumbnailUrls } from '@/lib/supabase/storage';
import { getPreferenceClusters, getInteractedPaperUuids } from '@/services/interactions.service';
import type { FeedResponse } from '@/types/recommendation';
import type { MinimalPaper } from '@/types/paper';

// ============================================================================
// CONSTANTS
// ============================================================================

/** Weight for semantic similarity in the scoring formula */
const SIMILARITY_WEIGHT = 0.33;

/** Weight for author popularity (max h-index) in the scoring formula */
const AUTHOR_POPULARITY_WEIGHT = 0.33;

/** Weight for recency in the scoring formula */
const RECENCY_WEIGHT = 0.33;

/** Weight for HuggingFace upvotes in the scoring formula */
const HF_UPVOTES_WEIGHT = 0.33;

/** H-index value that produces a max author popularity score of 1.0 */
const H_INDEX_CAP = 50;

/** Half-life in days for the recency exponential decay */
const RECENCY_HALF_LIFE_DAYS = 7;

/** Multiplier for ANN candidates relative to page size (fetches limit*2 total across clusters) */
const ANN_CANDIDATE_MULTIPLIER = 2;

/** Max boost from cluster weight on similarity score. Dominant cluster (weight ~0.6)
 *  gets similarity multiplied by ~1.18, minor cluster (weight ~0.1) by ~1.03. */
const CLUSTER_WEIGHT_BOOST = 0.3;

// ============================================================================
// TYPES
// ============================================================================

/** A user preference cluster with raw embedding and normalized weight */
interface PreferenceVector {
  embedding: number[];
  weight: number;
  clusterIndex: number;
}

/** A paper with all computed scoring components */
interface ScoredPaper {
  paper: MinimalPaper;
  score: number;
  recencyScore: number;
  authorPopularityScore: number;
  hfUpvotesScore: number;
  similarityScore: number;
  sourceClusterIndex: number | null;
  isExploration: boolean;
  finishedAt: Date;
  upvotes: number | null;
  maxAuthorHIndex: number | null;
}

/** Raw row from the match_papers_by_embedding RPC or cold-start query */
interface CandidateRow {
  paperUuid: string;
  title: string | null;
  authors: string | null;
  finishedAt: Date;
  embedding: number[];
  signals: Record<string, unknown> | null;
  similarity: number;
  sourceClusterIndex: number | null;
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
  // Merge previously interacted paper UUIDs into the exclude list
  if (userId) {
    const interactedUuids = await getInteractedPaperUuids(userId);
    const mergedExcludes = new Set([...excludePaperUuids, ...interactedUuids]);
    excludePaperUuids = Array.from(mergedExcludes);
  }

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

  // Return up to limit items; each request fetches fresh candidates via excludes
  const pageItems = diversified.slice(0, limit);
  const hasMore = diversified.length > limit;

  // Look up slugs for the page items
  const paperUuids = pageItems.map((sp) => sp.paper.paperUuid);
  const slugMap = await fetchSlugMap(paperUuids);

  // Batch-fetch signed thumbnail URLs in a single API call
  const thumbnailMap = await getPaperThumbnailUrls(paperUuids);

  const items: MinimalPaper[] = pageItems.map((sp) => ({
    ...sp.paper,
    slug: slugMap.get(sp.paper.paperUuid) ?? null,
    thumbnailUrl: thumbnailMap.get(sp.paper.paperUuid) ?? null,
    scoreBreakdown: {
      score: sp.score,
      similarityScore: sp.similarityScore,
      authorPopularityScore: sp.authorPopularityScore,
      hfUpvotesScore: sp.hfUpvotesScore,
      recencyScore: sp.recencyScore,
      isExploration: sp.isExploration,
      sourceClusterIndex: sp.sourceClusterIndex,
      finishedAt: sp.finishedAt.toISOString(),
      upvotes: sp.upvotes,
      maxAuthorHIndex: sp.maxAuthorHIndex,
    },
  }));

  return { items, page, limit, hasMore };
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Fetches the user's preference clusters and returns raw embeddings with normalized weights.
 * Weights are normalized to sum to 1 so no single cluster dominates ANN search.
 * @param userId - Supabase auth user ID
 * @returns Array of preference vectors with raw embeddings and normalized weights
 */
async function buildPreferenceVectors(userId: string): Promise<PreferenceVector[]> {
  const clusters = await getPreferenceClusters(userId);
  if (clusters.length === 0) return [];

  const totalWeight = clusters.reduce((sum, c) => sum + c.weight, 0);

  return clusters.map((cluster) => ({
    embedding: cluster.embedding,
    weight: totalWeight > 0 ? cluster.weight / totalWeight : 1 / clusters.length,
    clusterIndex: cluster.clusterIndex,
  }));
}

/**
 * Fetches candidate papers for ranking.
 * With preference vectors: fetches ANN candidates + exploration candidates.
 * Without (cold start): falls back to most recent papers.
 * @param excludePaperUuids - Paper UUIDs to exclude from results
 * @param preferenceVectors - Preference vectors with raw embeddings
 * @param limit - Desired page size (cold-start fetches limit*3)
 * @returns Array of candidate rows (ANN + exploration mixed)
 */
async function fetchCandidates(
  excludePaperUuids: string[],
  preferenceVectors: PreferenceVector[],
  limit: number
): Promise<CandidateRow[]> {
  if (preferenceVectors.length > 0) {
    const candidatesPerCluster = Math.ceil(
      (limit * ANN_CANDIDATE_MULTIPLIER) / preferenceVectors.length
    );
    const annCandidates = await fetchCandidatesFromANN(
      excludePaperUuids, preferenceVectors, candidatesPerCluster
    );

    // Fetch exploration candidates (multi-signal: recent + popular + upvoted)
    const annUuids = annCandidates.map((c) => c.paperUuid);
    const explorationCandidates = await fetchExplorationCandidates(
      [...excludePaperUuids, ...annUuids],
      limit
    );

    // If ANN returned nothing, exploration alone keeps the feed alive
    return [...annCandidates, ...explorationCandidates];
  }
  return fetchColdStartCandidates(excludePaperUuids, limit);
}

/**
 * Fetches candidates via ANN similarity search for each preference vector.
 * Uses raw (unscaled) embeddings and tags each candidate with its source cluster.
 * Deduplicates results across clusters (keeps highest similarity).
 * @param excludePaperUuids - Paper UUIDs to exclude
 * @param preferenceVectors - Preference vectors with raw embeddings
 * @returns Deduplicated candidate rows tagged with sourceClusterIndex
 */
async function fetchCandidatesFromANN(
  excludePaperUuids: string[],
  preferenceVectors: PreferenceVector[],
  candidatesPerCluster: number
): Promise<CandidateRow[]> {
  const supabase = await createClient();

  // Query each cluster in parallel using raw embeddings
  const clusterResults = await Promise.all(
    preferenceVectors.map(async (pv) => {
      const vectorString = `[${pv.embedding.join(',')}]`;

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { data, error } = await (supabase.rpc as any)(
        'match_papers_by_embedding',
        {
          query_embedding: vectorString,
          match_count: candidatesPerCluster,
          exclude_uuids: excludePaperUuids,
        }
      );

      if (error) {
        throw new Error(`match_papers_by_embedding RPC failed: ${error.message}`);
      }

      return {
        clusterIndex: pv.clusterIndex,
        rows: (data ?? []) as {
          paper_uuid: string;
          title: string | null;
          authors: string | null;
          finished_at: string;
          embedding: string;
          signals: Record<string, unknown> | null;
          similarity: number;
        }[],
      };
    })
  );

  // Deduplicate across clusters, keeping highest similarity
  const candidateMap = new Map<string, CandidateRow>();

  for (const { clusterIndex, rows } of clusterResults) {
    for (const row of rows) {
      const existing = candidateMap.get(row.paper_uuid);
      if (!existing || row.similarity > existing.similarity) {
        candidateMap.set(row.paper_uuid, {
          paperUuid: row.paper_uuid,
          title: row.title,
          authors: row.authors,
          finishedAt: new Date(row.finished_at),
          embedding: parseEmbeddingString(row.embedding),
          signals: row.signals,
          similarity: row.similarity,
          sourceClusterIndex: clusterIndex,
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
    .select('paper_uuid, title, authors, finished_at, signals')
    .in('status', ['completed', 'partially_completed'])
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
    signals: Record<string, unknown> | null;
  }[]).map((row) => ({
    paperUuid: row.paper_uuid,
    title: row.title,
    authors: row.authors,
    finishedAt: new Date(row.finished_at),
    embedding: [],
    signals: row.signals,
    similarity: 0,
    sourceClusterIndex: null,
  }));
}

/**
 * Fetches exploration candidates using three signals for diversity:
 * most recent, most popular (h-index), and most upvoted (HF upvotes).
 * Deduplicates across the three pools and returns merged candidates.
 * @param excludePaperUuids - Paper UUIDs to exclude (already shown + ANN results)
 * @param count - Number of candidates to fetch per signal
 * @returns Deduplicated candidate rows with similarity=0 and sourceClusterIndex=null
 */
async function fetchExplorationCandidates(
  excludePaperUuids: string[],
  count: number
): Promise<CandidateRow[]> {
  const supabase = await createClient();

  const baseFilters = (query: ReturnType<typeof supabase.from>) => {
    let q = query
      .select('paper_uuid, title, authors, finished_at, signals')
      .in('status', ['completed', 'partially_completed'])
      .limit(count);

    if (excludePaperUuids.length > 0) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      q = (q as any).not('paper_uuid', 'in', `(${excludePaperUuids.join(',')})`);
    }
    return q;
  };

  // Fetch three pools in parallel: recent, popular, upvoted
  const [recentResult, popularResult, upvotedResult] = await Promise.all([
    baseFilters(supabase.from('papers'))
      .order('finished_at', { ascending: false }),
    baseFilters(supabase.from('papers'))
      .order('signals->max_author_h_index', { ascending: false, nullsFirst: false }),
    baseFilters(supabase.from('papers'))
      .order('signals->hf_upvotes', { ascending: false, nullsFirst: false }),
  ]);

  if (recentResult.error) throw new Error(`Exploration (recent) fetch failed: ${recentResult.error.message}`);
  if (popularResult.error) throw new Error(`Exploration (popular) fetch failed: ${popularResult.error.message}`);
  if (upvotedResult.error) throw new Error(`Exploration (upvoted) fetch failed: ${upvotedResult.error.message}`);

  // Deduplicate across the three pools
  const candidateMap = new Map<string, CandidateRow>();

  for (const row of [
    ...(recentResult.data ?? []),
    ...(popularResult.data ?? []),
    ...(upvotedResult.data ?? []),
  ] as {
    paper_uuid: string;
    title: string | null;
    authors: string | null;
    finished_at: string;
    signals: Record<string, unknown> | null;
  }[]) {
    if (!candidateMap.has(row.paper_uuid)) {
      candidateMap.set(row.paper_uuid, {
        paperUuid: row.paper_uuid,
        title: row.title,
        authors: row.authors,
        finishedAt: new Date(row.finished_at),
        embedding: [],
        signals: row.signals,
        similarity: 0,
        sourceClusterIndex: null,
      });
    }
  }

  return Array.from(candidateMap.values());
}

/**
 * Scores candidates with a weighted blend of similarity, author popularity,
 * recency, and HuggingFace upvotes. Each term is weighted at 0.33, so the
 * max raw score is ~1.32 -- capped at 1.0.
 * @param candidates - Candidate rows to score
 * @param preferenceVectors - User's preference vectors (empty for cold start)
 * @returns Scored and sorted papers
 */
async function scoreCandidates(
  candidates: CandidateRow[],
  preferenceVectors: PreferenceVector[]
): Promise<ScoredPaper[]> {
  const now = Date.now();

  const candidateUuids = candidates.map((c) => c.paperUuid);
  const thumbnailMap = await getPaperThumbnailUrls(candidateUuids);

  // Build a lookup from clusterIndex -> normalized weight for cluster-weight boost
  const clusterWeightMap = new Map<number, number>();
  for (const pv of preferenceVectors) {
    clusterWeightMap.set(pv.clusterIndex, pv.weight);
  }

  const scored: ScoredPaper[] = candidates.map((candidate) => {
    // Recency: exponential decay with 7-day half-life
    const daysSinceFinished = (now - candidate.finishedAt.getTime()) / (1000 * 60 * 60 * 24);
    const recencyScore = Math.exp(-daysSinceFinished * Math.LN2 / RECENCY_HALF_LIFE_DAYS);

    // Author popularity: max h-index from pre-computed signals, normalized to [0, 1]
    const maxAuthorHIndex = (candidate.signals?.max_author_h_index as number) ?? null;
    const authorPopularityScore = maxAuthorHIndex !== null
      ? Math.min(maxAuthorHIndex / H_INDEX_CAP, 1.0)
      : 0;

    // HuggingFace upvotes: min(upvotes/100, 1.0), 0 if no data
    const upvotes = extractUpvotes(candidate.signals);
    const hfUpvotesScore = upvotes !== null ? Math.min(upvotes / 100, 1.0) : 0;

    // Similarity: apply cluster-weight boost for ANN candidates, 0 for exploration
    const isExploration = candidate.sourceClusterIndex === null && candidate.similarity === 0
      && preferenceVectors.length > 0;
    let similarityScore = candidate.similarity;
    if (candidate.sourceClusterIndex !== null) {
      const clusterWeight = clusterWeightMap.get(candidate.sourceClusterIndex) ?? 0;
      similarityScore = candidate.similarity * (1 + CLUSTER_WEIGHT_BOOST * clusterWeight);
    }

    // Weighted blend (4 terms x 0.33 = max ~1.32), capped at 1.0
    const rawScore =
      SIMILARITY_WEIGHT * similarityScore +
      AUTHOR_POPULARITY_WEIGHT * authorPopularityScore +
      RECENCY_WEIGHT * recencyScore +
      HF_UPVOTES_WEIGHT * hfUpvotesScore;
    const score = Math.min(rawScore, 1.0);

    const paper: MinimalPaper = {
      paperUuid: candidate.paperUuid,
      title: candidate.title,
      authors: candidate.authors,
      slug: null,
      thumbnailUrl: thumbnailMap.get(candidate.paperUuid) ?? null,
    };

    return {
      paper, score, recencyScore, authorPopularityScore, hfUpvotesScore,
      similarityScore, sourceClusterIndex: candidate.sourceClusterIndex,
      isExploration, finishedAt: candidate.finishedAt, upvotes,
      maxAuthorHIndex,
    } satisfies ScoredPaper;
  });

  // Sort descending by score
  scored.sort((a, b) => b.score - a.score);

  return scored;
}

/**
 * Injects diversity into the ranked feed using sourceClusterIndex and exploration papers.
 * Pass 1: At every 5th position, swap in a paper from a non-dominant cluster.
 * Pass 2: Interleave exploration papers at regular intervals.
 * @param rankedPapers - Score-sorted papers
 * @param preferenceVectors - User's preference vectors
 * @returns Papers with diversity injected
 */
function injectDiversity(
  rankedPapers: ScoredPaper[],
  preferenceVectors: PreferenceVector[]
): ScoredPaper[] {
  if (preferenceVectors.length === 0 || rankedPapers.length === 0) {
    return rankedPapers;
  }

  const result = [...rankedPapers];

  // Pass 1: cluster diversity -- swap non-dominant cluster papers into every 5th position
  if (preferenceVectors.length >= 2) {
    // Find dominant cluster (most papers assigned to it)
    const clusterCounts = new Map<number, number>();
    for (const sp of result) {
      if (sp.sourceClusterIndex !== null) {
        clusterCounts.set(sp.sourceClusterIndex, (clusterCounts.get(sp.sourceClusterIndex) ?? 0) + 1);
      }
    }
    let dominantCluster = preferenceVectors[0].clusterIndex;
    let maxCount = 0;
    for (const [cluster, count] of clusterCounts) {
      if (count > maxCount) {
        maxCount = count;
        dominantCluster = cluster;
      }
    }

    const used = new Set<number>();
    for (let pos = 4; pos < result.length; pos += 5) {
      let bestIdx = -1;
      let bestScore = -Infinity;

      for (let i = pos + 1; i < result.length; i++) {
        if (!used.has(i)
          && result[i].sourceClusterIndex !== null
          && result[i].sourceClusterIndex !== dominantCluster
          && result[i].score > bestScore) {
          bestScore = result[i].score;
          bestIdx = i;
        }
      }

      if (bestIdx !== -1) {
        used.add(pos);
        const picked = result.splice(bestIdx, 1)[0];
        result.splice(pos, 0, picked);
      }
    }
  }

  // Pass 2: interleave exploration papers at regular intervals
  const explorationPapers: ScoredPaper[] = [];
  const nonExploration: ScoredPaper[] = [];
  for (const sp of result) {
    if (sp.isExploration) {
      explorationPapers.push(sp);
    } else {
      nonExploration.push(sp);
    }
  }

  if (explorationPapers.length === 0) return result;

  // Insert one exploration paper every ~5 positions
  const interval = Math.max(3, Math.floor(nonExploration.length / explorationPapers.length));
  const final: ScoredPaper[] = [];
  let explIdx = 0;
  for (let i = 0; i < nonExploration.length; i++) {
    final.push(nonExploration[i]);
    // After every `interval` non-exploration papers, insert an exploration paper
    if ((i + 1) % interval === 0 && explIdx < explorationPapers.length) {
      final.push(explorationPapers[explIdx]);
      explIdx++;
    }
  }
  // Append any remaining exploration papers at the end
  while (explIdx < explorationPapers.length) {
    final.push(explorationPapers[explIdx]);
    explIdx++;
  }

  return final;
}

/**
 * Extracts the raw HuggingFace upvote count from the signals dict.
 * @param signals - The signals JSON dict (e.g. {"hf_upvotes": 42})
 * @returns Raw upvote count or null if not available
 */
function extractUpvotes(signals: Record<string, unknown> | null): number | null {
  if (!signals) return null;
  const upvotes = signals.hf_upvotes;
  return typeof upvotes === 'number' ? upvotes : null;
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
