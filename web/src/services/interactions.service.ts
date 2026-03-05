/**
 * Interactions Service
 *
 * Server-side service for persisting user interaction events and managing
 * user preference clusters.
 *
 * Responsibilities:
 * - Batch-insert interaction events into the user_interactions table
 * - Update preference clusters based on interacted paper embeddings
 * - Retrieve preference clusters with daily weight decay
 */

import { createClient } from '@/lib/supabase/server';
import type { InteractionEvent, UserPreferenceCluster } from '@/types/recommendation';

// ============================================================================
// CONSTANTS
// ============================================================================

/** Maximum number of preference clusters per user */
const MAX_CLUSTERS = 5;

/** Similarity threshold for assigning a paper to an existing cluster */
const SIMILARITY_THRESHOLD = 0.7;

/** Weight given to the existing cluster centroid when updating */
const CENTROID_OLD_WEIGHT = 0.8;

/** Weight given to the new paper embedding when updating a cluster centroid */
const CENTROID_NEW_WEIGHT = 0.2;

/** Daily decay factor applied to cluster weights */
const DAILY_WEIGHT_DECAY = 0.95;

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * Batch-inserts interaction events into the user_interactions table.
 * @param userId - Supabase auth.uid() of the user (anonymous or permanent)
 * @param events - Array of interaction events to persist
 */
export async function saveInteractions(
  userId: string,
  events: InteractionEvent[]
): Promise<void> {
  if (events.length === 0) return;

  const supabase = await createClient();

  const rows = events.map((event) => ({
    user_id: userId,
    paper_uuid: event.paperUuid,
    interaction_type: event.interactionType,
    metadata: event.metadata ?? null,
  }));

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { error } = await (supabase.from('user_interactions') as any).insert(rows);

  if (error) {
    throw new Error(`Failed to save interactions: ${error.message}`);
  }
}

/**
 * Updates preference clusters for a user based on newly interacted paper embeddings.
 * For each paper embedding:
 *  - If most similar cluster > 0.7: merge into that cluster
 *  - If <= 0.7 and fewer than 5 clusters: create a new cluster
 *  - If <= 0.7 and 5 clusters exist: replace the weakest cluster
 * @param userId - Supabase auth.uid() of the user
 * @param interactedPaperUuids - UUIDs of papers the user just interacted with
 */
export async function updatePreferenceClusters(
  userId: string,
  interactedPaperUuids: string[]
): Promise<void> {
  if (interactedPaperUuids.length === 0) return;

  const supabase = await createClient();

  // Fetch embeddings for the interacted papers
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: papers, error: papersError } = await (supabase.from('papers') as any)
    .select('paper_uuid, embedding')
    .in('paper_uuid', interactedPaperUuids)
    .not('embedding', 'is', null);

  if (papersError) {
    throw new Error(`Failed to fetch paper embeddings: ${papersError.message}`);
  }

  if (!papers || papers.length === 0) return;

  // Fetch existing clusters for this user
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: existingClusters, error: clustersError } = await (supabase
    .from('user_preference_clusters') as any)
    .select('id, cluster_index, embedding, weight, interaction_count, updated_at')
    .eq('user_id', userId)
    .order('cluster_index', { ascending: true });

  if (clustersError) {
    throw new Error(`Failed to fetch preference clusters: ${clustersError.message}`);
  }

  // Parse cluster embeddings from string to number[]
  interface ClusterRow {
    id: number;
    cluster_index: number;
    embedding: string;
    weight: number;
    interaction_count: number;
    updated_at: string;
  }

  let clusters: {
    id: number;
    clusterIndex: number;
    embedding: number[];
    weight: number;
    interactionCount: number;
  }[] = ((existingClusters ?? []) as ClusterRow[]).map((c) => ({
    id: c.id,
    clusterIndex: c.cluster_index,
    embedding: parseEmbeddingString(c.embedding),
    weight: c.weight,
    interactionCount: c.interaction_count,
  }));

  // Process each paper embedding
  for (const paper of papers as { paper_uuid: string; embedding: string }[]) {
    const paperEmbedding = parseEmbeddingString(paper.embedding);

    if (clusters.length === 0) {
      // First cluster: create it at index 0
      const newIndex = 0;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { data: inserted, error: insertError } = await (supabase
        .from('user_preference_clusters') as any)
        .insert({
          user_id: userId,
          cluster_index: newIndex,
          embedding: formatEmbeddingString(paperEmbedding),
          weight: 1.0,
          interaction_count: 1,
          updated_at: new Date().toISOString(),
        })
        .select('id')
        .single();

      if (insertError) {
        throw new Error(`Failed to create cluster: ${insertError.message}`);
      }

      clusters.push({
        id: inserted.id,
        clusterIndex: newIndex,
        embedding: paperEmbedding,
        weight: 1.0,
        interactionCount: 1,
      });
      continue;
    }

    // Find the most similar cluster
    let maxSimilarity = -1;
    let bestClusterIdx = -1;
    for (let i = 0; i < clusters.length; i++) {
      const sim = cosineSimilarity(paperEmbedding, clusters[i].embedding);
      if (sim > maxSimilarity) {
        maxSimilarity = sim;
        bestClusterIdx = i;
      }
    }

    if (maxSimilarity > SIMILARITY_THRESHOLD) {
      // Merge into the most similar cluster
      const cluster = clusters[bestClusterIdx];
      const newEmbedding = blendEmbeddings(cluster.embedding, paperEmbedding);
      const newWeight = cluster.weight + 1;
      const newCount = cluster.interactionCount + 1;

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { error: updateError } = await (supabase
        .from('user_preference_clusters') as any)
        .update({
          embedding: formatEmbeddingString(newEmbedding),
          weight: newWeight,
          interaction_count: newCount,
          updated_at: new Date().toISOString(),
        })
        .eq('id', cluster.id);

      if (updateError) {
        throw new Error(`Failed to update cluster: ${updateError.message}`);
      }

      // Update local state
      clusters[bestClusterIdx] = {
        ...cluster,
        embedding: newEmbedding,
        weight: newWeight,
        interactionCount: newCount,
      };
    } else if (clusters.length < MAX_CLUSTERS) {
      // Create a new cluster at the next available index
      const usedIndices = new Set(clusters.map((c) => c.clusterIndex));
      let newIndex = 0;
      while (usedIndices.has(newIndex)) newIndex++;

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { data: inserted, error: insertError } = await (supabase
        .from('user_preference_clusters') as any)
        .insert({
          user_id: userId,
          cluster_index: newIndex,
          embedding: formatEmbeddingString(paperEmbedding),
          weight: 1.0,
          interaction_count: 1,
          updated_at: new Date().toISOString(),
        })
        .select('id')
        .single();

      if (insertError) {
        throw new Error(`Failed to create cluster: ${insertError.message}`);
      }

      clusters.push({
        id: inserted.id,
        clusterIndex: newIndex,
        embedding: paperEmbedding,
        weight: 1.0,
        interactionCount: 1,
      });
    } else {
      // Replace the cluster with the lowest weight
      let minWeight = Infinity;
      let weakestIdx = 0;
      for (let i = 0; i < clusters.length; i++) {
        if (clusters[i].weight < minWeight) {
          minWeight = clusters[i].weight;
          weakestIdx = i;
        }
      }

      const weakest = clusters[weakestIdx];

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { error: replaceError } = await (supabase
        .from('user_preference_clusters') as any)
        .update({
          embedding: formatEmbeddingString(paperEmbedding),
          weight: 1.0,
          interaction_count: 1,
          updated_at: new Date().toISOString(),
        })
        .eq('id', weakest.id);

      if (replaceError) {
        throw new Error(`Failed to replace cluster: ${replaceError.message}`);
      }

      // Update local state
      clusters[weakestIdx] = {
        ...weakest,
        embedding: paperEmbedding,
        weight: 1.0,
        interactionCount: 1,
      };
    }
  }
}

/**
 * Returns the user's preference clusters with daily weight decay applied.
 * Weight is multiplied by 0.95^(days since last update).
 * @param userId - Supabase auth.uid() of the user
 * @returns Array of preference clusters with decayed weights
 */
export async function getPreferenceClusters(
  userId: string
): Promise<UserPreferenceCluster[]> {
  const supabase = await createClient();

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: rows, error } = await (supabase
    .from('user_preference_clusters') as any)
    .select('cluster_index, embedding, weight, interaction_count, updated_at')
    .eq('user_id', userId)
    .order('cluster_index', { ascending: true });

  if (error) {
    throw new Error(`Failed to fetch preference clusters: ${error.message}`);
  }

  if (!rows || rows.length === 0) return [];

  const now = Date.now();

  return (rows as {
    cluster_index: number;
    embedding: string;
    weight: number;
    interaction_count: number;
    updated_at: string;
  }[]).map((row) => {
    const daysSinceUpdate = (now - new Date(row.updated_at).getTime()) / (1000 * 60 * 60 * 24);
    const decayedWeight = row.weight * Math.pow(DAILY_WEIGHT_DECAY, daysSinceUpdate);

    return {
      clusterIndex: row.cluster_index,
      embedding: parseEmbeddingString(row.embedding),
      weight: decayedWeight,
      interactionCount: row.interaction_count,
      updatedAt: row.updated_at,
    };
  });
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Computes cosine similarity between two vectors.
 * @param a - First vector
 * @param b - Second vector
 * @returns Cosine similarity in [-1, 1]
 */
export function cosineSimilarity(a: number[], b: number[]): number {
  let dot = 0;
  let magA = 0;
  let magB = 0;

  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    magA += a[i] * a[i];
    magB += b[i] * b[i];
  }

  const denominator = Math.sqrt(magA) * Math.sqrt(magB);
  if (denominator === 0) return 0;

  return dot / denominator;
}

/**
 * Blends an existing cluster centroid with a new paper embedding.
 * Uses weighted average: 0.8 * old + 0.2 * new.
 * @param oldEmbedding - Existing cluster centroid
 * @param newEmbedding - New paper embedding to merge in
 * @returns Blended embedding vector
 */
function blendEmbeddings(oldEmbedding: number[], newEmbedding: number[]): number[] {
  const result = new Array<number>(oldEmbedding.length);
  for (let i = 0; i < oldEmbedding.length; i++) {
    result[i] = CENTROID_OLD_WEIGHT * oldEmbedding[i] + CENTROID_NEW_WEIGHT * newEmbedding[i];
  }
  return result;
}

/**
 * Parses a Supabase vector string (e.g. "[0.1,0.2,...]") into a number array.
 * @param embeddingStr - The string representation of the embedding vector
 * @returns Parsed number array
 */
function parseEmbeddingString(embeddingStr: string): number[] {
  // Supabase returns vectors as strings like "[0.1,0.2,0.3]"
  const cleaned = embeddingStr.replace(/^\[|\]$/g, '');
  return cleaned.split(',').map(Number);
}

/**
 * Formats a number array as a string for Supabase vector storage.
 * @param embedding - The embedding vector as a number array
 * @returns String representation like "[0.1,0.2,0.3]"
 */
function formatEmbeddingString(embedding: number[]): string {
  return `[${embedding.join(',')}]`;
}
