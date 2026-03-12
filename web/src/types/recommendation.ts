/**
 * Recommendation System Types
 *
 * DTOs for the feed recommendation system: interaction events, feed requests/responses,
 * and user preference clusters.
 *
 * Responsibilities:
 * - Define interaction event types for tracking user signals (expand, read, save)
 * - Define feed request/response DTOs for the ranked feed endpoint
 * - Define user preference cluster shape for server-side ranking
 */

import type { MinimalPaper } from './paper';

// ============================================================================
// CONSTANTS / TYPES
// ============================================================================

/** Types of user interactions tracked by the system */
export type InteractionType = 'expanded' | 'read' | 'saved';

// ============================================================================
// INTERFACES - Interaction Events
// ============================================================================

/**
 * A single user interaction event to be sent to the backend.
 */
export interface InteractionEvent {
  /** UUID of the paper that was interacted with */
  paperUuid: string;
  /** Type of interaction */
  interactionType: InteractionType;
  /** Optional metadata (e.g. { readingRatio: 0.7 } for 'read' type) */
  metadata?: Record<string, unknown>;
}

// ============================================================================
// INTERFACES - Score Breakdown
// ============================================================================

/**
 * Breakdown of how a paper's feed score was calculated.
 * Score = 0.33 * similarity + 0.33 * authorPopularity + 0.33 * recency + 0.33 * hfUpvotes, capped at 1.0.
 */
export interface ScoreBreakdown {
  /** Final weighted score (capped at 1.0) */
  score: number;
  /** Semantic similarity component (from ANN search + cluster-weight boost) */
  similarityScore: number;
  /** Author popularity component: min(maxHIndex / 50, 1.0) */
  authorPopularityScore: number;
  /** HuggingFace upvotes component: min(upvotes / 100, 1.0) */
  hfUpvotesScore: number;
  /** Recency component (exponential decay with 7-day half-life) */
  recencyScore: number;
  /** Whether this paper is an exploration candidate (outside known interests) */
  isExploration: boolean;
  /** Which preference cluster sourced this paper (null for exploration/cold-start) */
  sourceClusterIndex: number | null;
  /** When the paper finished processing (used for recency calculation) */
  finishedAt: string;
  /** Raw HuggingFace upvote count (null if no signal available) */
  upvotes: number | null;
  /** Max h-index across the paper's authors (null if no author data) */
  maxAuthorHIndex: number | null;
}

// ============================================================================
// INTERFACES - Feed Request/Response
// ============================================================================

/**
 * Request body for the ranked feed endpoint.
 */
export interface FeedRequest {
  /** Page number (1-indexed) */
  page: number;
  /** Number of items per page */
  limit: number;
  /** Paper UUIDs already shown in the session (to exclude from results) */
  excludePaperUuids: string[];
}

/**
 * Response from the ranked feed endpoint.
 */
export interface FeedResponse {
  /** Ranked papers for the current page */
  items: MinimalPaper[];
  /** Current page number */
  page: number;
  /** Items per page */
  limit: number;
  /** Whether more pages are available */
  hasMore: boolean;
}

// ============================================================================
// INTERFACES - User Preference Clusters
// ============================================================================

/**
 * A single preference cluster representing a user interest area.
 * Each user has 1-5 clusters that evolve based on interactions.
 */
export interface UserPreferenceCluster {
  /** Cluster index (0-4) */
  clusterIndex: number;
  /** 1536-dimensional embedding vector representing the cluster centroid */
  embedding: number[];
  /** Recency-decayed strength of this cluster */
  weight: number;
  /** Number of interactions that contributed to this cluster */
  interactionCount: number;
  /** ISO timestamp of last cluster update */
  updatedAt: string;
}
