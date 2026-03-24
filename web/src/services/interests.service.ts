/**
 * Interests Service
 *
 * Server-side service for on-the-fly clustering of a user's interacted papers.
 * Uses k-means on paper embeddings to group papers by topic similarity.
 *
 * Responsibilities:
 * - Fetch all papers a user has interacted with (opened, saved, read)
 * - Run k-means clustering on paper embeddings
 * - Return clusters with paper metadata for display
 */

import { createClient } from '@/lib/supabase/server';
import { getPaperThumbnailUrls } from '@/lib/supabase/storage';
import type {
  ClusteredPaper,
  InterestCluster,
  InterestClustersResponse,
} from '@/types/interests';
import type { MinimalPaper } from '@/types/paper';

// ============================================================================
// CONSTANTS
// ============================================================================

/** Maximum iterations for k-means before stopping */
const MAX_KMEANS_ITERATIONS = 20;

/** Interaction types to include (excludes 'seen') */
const INCLUDED_INTERACTION_TYPES = ['expanded', 'read', 'saved'];

/** Default number of similar papers to return in search */
const DEFAULT_SEARCH_LIMIT = 20;

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * Fetches all papers the user has interacted with and clusters them using k-means.
 * @param userId - Supabase auth.uid() of the user
 * @param maxClusters - Maximum number of clusters to create (actual k = min(maxClusters, numPapers))
 * @returns Clusters of papers grouped by embedding similarity
 */
export async function getInterestClusters(
  userId: string,
  maxClusters: number
): Promise<InterestClustersResponse> {
  const supabase = await createClient();

  // Step 1: Get distinct paper UUIDs the user has interacted with
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: interactionRows, error: interactionError } = await (supabase
    .from('user_interactions') as any)
    .select('paper_uuid')
    .eq('user_id', userId)
    .in('interaction_type', INCLUDED_INTERACTION_TYPES);

  if (interactionError) {
    throw new Error(`Failed to fetch interactions: ${interactionError.message}`);
  }

  const paperUuids = [
    ...new Set(
      ((interactionRows ?? []) as { paper_uuid: string }[]).map((r) => r.paper_uuid)
    ),
  ];

  if (paperUuids.length === 0) {
    return { clusters: [], totalPapers: 0 };
  }

  // Step 2: Fetch paper details and embeddings
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: papersData, error: papersError } = await (supabase
    .from('papers') as any)
    .select('paper_uuid, title, authors, embedding')
    .in('paper_uuid', paperUuids)
    .not('embedding', 'is', null);

  if (papersError) {
    throw new Error(`Failed to fetch papers: ${papersError.message}`);
  }

  const papers = (papersData ?? []) as {
    paper_uuid: string;
    title: string | null;
    authors: string | null;
    embedding: string;
  }[];

  if (papers.length === 0) {
    return { clusters: [], totalPapers: 0 };
  }

  // Step 3: Fetch slugs and thumbnails in parallel
  const uuidsWithEmbeddings = papers.map((p) => p.paper_uuid);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [slugsResult, thumbnailMap] = await Promise.all([
    (supabase.from('paper_slugs') as any)
      .select('paper_uuid, slug')
      .in('paper_uuid', uuidsWithEmbeddings),
    getPaperThumbnailUrls(uuidsWithEmbeddings),
  ]);

  if (slugsResult.error) {
    throw new Error(`Failed to fetch slugs: ${slugsResult.error.message}`);
  }

  const slugMap = new Map<string, string>();
  for (const s of (slugsResult.data ?? []) as { paper_uuid: string; slug: string }[]) {
    slugMap.set(s.paper_uuid, s.slug);
  }

  // Step 4: Parse embeddings and run k-means
  const embeddings = papers.map((p) => parseEmbeddingString(p.embedding));
  const k = Math.min(maxClusters, papers.length);
  const { assignments, centroids } = kMeans(embeddings, k);

  // Step 5: Group papers by cluster assignment
  const clusterMap = new Map<number, ClusteredPaper[]>();

  for (let i = 0; i < papers.length; i++) {
    const clusterIdx = assignments[i];
    const paper = papers[i];

    const clusteredPaper: ClusteredPaper = {
      paperUuid: paper.paper_uuid,
      title: paper.title,
      authors: paper.authors,
      slug: slugMap.get(paper.paper_uuid) ?? null,
      thumbnailUrl: thumbnailMap.get(paper.paper_uuid) ?? null,
    };

    const existing = clusterMap.get(clusterIdx);
    if (existing) {
      existing.push(clusteredPaper);
    } else {
      clusterMap.set(clusterIdx, [clusteredPaper]);
    }
  }

  // Build response, re-index clusters sequentially (0, 1, 2, ...)
  const clusters: InterestCluster[] = [];
  let idx = 0;
  for (const [originalIdx, clusterPapers] of clusterMap) {
    clusters.push({
      clusterIndex: idx,
      papers: clusterPapers,
      centroid: centroids[originalIdx],
    });
    idx++;
  }

  return { clusters, totalPapers: papers.length };
}

/**
 * Searches for papers similar to a given centroid embedding,
 * excluding papers the user has already interacted with.
 * @param userId - Supabase auth.uid() of the user
 * @param embedding - Centroid embedding vector to search with
 * @param limit - Maximum number of results to return
 * @returns Ranked list of similar papers as MinimalPaper items
 */
export async function searchSimilarPapers(
  userId: string,
  embedding: number[],
  limit: number = DEFAULT_SEARCH_LIMIT
): Promise<MinimalPaper[]> {
  const supabase = await createClient();

  // Get papers the user has already interacted with (to exclude)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: interactionRows, error: interactionError } = await (supabase
    .from('user_interactions') as any)
    .select('paper_uuid')
    .eq('user_id', userId)
    .in('interaction_type', INCLUDED_INTERACTION_TYPES);

  if (interactionError) {
    throw new Error(`Failed to fetch interactions: ${interactionError.message}`);
  }

  const excludeUuids = [
    ...new Set(
      ((interactionRows ?? []) as { paper_uuid: string }[]).map((r) => r.paper_uuid)
    ),
  ];

  // Search for similar papers via the existing RPC
  const vectorString = `[${embedding.join(',')}]`;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data, error } = await (supabase.rpc as any)(
    'match_papers_by_embedding',
    {
      query_embedding: vectorString,
      match_count: limit,
      exclude_uuids: excludeUuids,
    }
  );

  if (error) {
    throw new Error(`match_papers_by_embedding RPC failed: ${error.message}`);
  }

  const rows = (data ?? []) as {
    paper_uuid: string;
    title: string | null;
    authors: string | null;
    similarity: number;
  }[];

  if (rows.length === 0) {
    return [];
  }

  // Fetch slugs and thumbnails in parallel
  const uuids = rows.map((r) => r.paper_uuid);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [slugsResult, thumbnailMap] = await Promise.all([
    (supabase.from('paper_slugs') as any)
      .select('paper_uuid, slug')
      .in('paper_uuid', uuids),
    getPaperThumbnailUrls(uuids),
  ]);

  if (slugsResult.error) {
    throw new Error(`Failed to fetch slugs: ${slugsResult.error.message}`);
  }

  const slugMap = new Map<string, string>();
  for (const s of (slugsResult.data ?? []) as { paper_uuid: string; slug: string }[]) {
    slugMap.set(s.paper_uuid, s.slug);
  }

  return rows.map((row) => ({
    paperUuid: row.paper_uuid,
    title: row.title,
    authors: row.authors,
    slug: slugMap.get(row.paper_uuid) ?? null,
    thumbnailUrl: thumbnailMap.get(row.paper_uuid) ?? null,
  }));
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Result of k-means clustering.
 */
interface KMeansResult {
  /** Cluster assignment for each embedding (index into centroids) */
  assignments: number[];
  /** Final centroid vectors */
  centroids: number[][];
}

/**
 * Runs k-means clustering on a set of embedding vectors.
 * Uses k-means++ initialization and Lloyd's algorithm.
 * @param embeddings - Array of embedding vectors (all same dimensionality)
 * @param k - Number of clusters to create
 * @returns Cluster assignments and final centroid vectors
 */
function kMeans(embeddings: number[][], k: number): KMeansResult {
  const n = embeddings.length;

  if (k >= n) {
    // Each paper gets its own cluster
    return {
      assignments: embeddings.map((_, i) => i),
      centroids: embeddings.map((e) => [...e]),
    };
  }

  // K-means++ initialization
  const centroids = kMeansPlusPlusInit(embeddings, k);

  let assignments = new Array<number>(n).fill(0);

  for (let iter = 0; iter < MAX_KMEANS_ITERATIONS; iter++) {
    // Assign each point to the nearest centroid
    const newAssignments = new Array<number>(n);
    for (let i = 0; i < n; i++) {
      let bestCluster = 0;
      let bestDist = Infinity;
      for (let c = 0; c < k; c++) {
        const dist = euclideanDistanceSquared(embeddings[i], centroids[c]);
        if (dist < bestDist) {
          bestDist = dist;
          bestCluster = c;
        }
      }
      newAssignments[i] = bestCluster;
    }

    // Check for convergence
    let changed = false;
    for (let i = 0; i < n; i++) {
      if (newAssignments[i] !== assignments[i]) {
        changed = true;
        break;
      }
    }
    assignments = newAssignments;

    if (!changed) break;

    // Recompute centroids
    const dim = embeddings[0].length;
    const sums = Array.from({ length: k }, () => new Array<number>(dim).fill(0));
    const counts = new Array<number>(k).fill(0);

    for (let i = 0; i < n; i++) {
      const c = assignments[i];
      counts[c]++;
      for (let d = 0; d < dim; d++) {
        sums[c][d] += embeddings[i][d];
      }
    }

    for (let c = 0; c < k; c++) {
      if (counts[c] === 0) continue;
      for (let d = 0; d < dim; d++) {
        centroids[c][d] = sums[c][d] / counts[c];
      }
    }
  }

  return { assignments, centroids };
}

/**
 * K-means++ initialization: picks initial centroids that are spread apart.
 * First centroid is random, subsequent ones are chosen proportional to
 * squared distance from the nearest existing centroid.
 * @param embeddings - Array of embedding vectors
 * @param k - Number of centroids to pick
 * @returns Array of k centroid vectors (copies of selected embeddings)
 */
function kMeansPlusPlusInit(embeddings: number[][], k: number): number[][] {
  const n = embeddings.length;
  const centroids: number[][] = [];

  // Pick first centroid randomly
  const firstIdx = Math.floor(Math.random() * n);
  centroids.push([...embeddings[firstIdx]]);

  // Pick remaining centroids
  for (let c = 1; c < k; c++) {
    // Compute squared distance from each point to nearest centroid
    const distances = new Array<number>(n);
    let totalDist = 0;

    for (let i = 0; i < n; i++) {
      let minDist = Infinity;
      for (let j = 0; j < centroids.length; j++) {
        const dist = euclideanDistanceSquared(embeddings[i], centroids[j]);
        if (dist < minDist) minDist = dist;
      }
      distances[i] = minDist;
      totalDist += minDist;
    }

    // Pick next centroid with probability proportional to squared distance
    let target = Math.random() * totalDist;
    let picked = 0;
    for (let i = 0; i < n; i++) {
      target -= distances[i];
      if (target <= 0) {
        picked = i;
        break;
      }
    }

    centroids.push([...embeddings[picked]]);
  }

  return centroids;
}

/**
 * Computes squared Euclidean distance between two vectors.
 * Skips the sqrt for performance since we only need relative comparisons.
 * @param a - First vector
 * @param b - Second vector
 * @returns Squared Euclidean distance
 */
function euclideanDistanceSquared(a: number[], b: number[]): number {
  let sum = 0;
  for (let i = 0; i < a.length; i++) {
    const diff = a[i] - b[i];
    sum += diff * diff;
  }
  return sum;
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
