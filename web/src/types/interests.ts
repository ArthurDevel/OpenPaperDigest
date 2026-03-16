/**
 * Interest Clustering Types
 *
 * DTOs for the on-the-fly interest clustering feature that groups
 * a user's interacted papers by topic similarity.
 *
 * Responsibilities:
 * - Define the shape of a clustered paper for display
 * - Define the cluster grouping structure
 * - Define the API response shape
 */

// ============================================================================
// INTERFACES
// ============================================================================

/**
 * A paper within a cluster, with display metadata.
 */
export interface ClusteredPaper {
  /** UUID of the paper */
  paperUuid: string;
  /** Paper title (null if missing) */
  title: string | null;
  /** Paper authors (null if missing) */
  authors: string | null;
  /** URL-friendly slug (null if no slug exists) */
  slug: string | null;
  /** Signed thumbnail URL (null if no thumbnail in storage) */
  thumbnailUrl: string | null;
}

/**
 * A single cluster containing related papers.
 */
export interface InterestCluster {
  /** Zero-based cluster index */
  clusterIndex: number;
  /** Papers assigned to this cluster */
  papers: ClusteredPaper[];
}

/**
 * Response from the interests clustering endpoint.
 */
export interface InterestClustersResponse {
  /** Array of clusters, each containing related papers */
  clusters: InterestCluster[];
  /** Total number of papers that were clustered */
  totalPapers: number;
}
