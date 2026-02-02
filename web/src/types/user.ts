/**
 * User-related type definitions for the Paper Summarizer application.
 *
 * Responsibilities:
 * - Define user list item types (papers saved by user)
 * - Define user request item types (papers requested by user)
 * - Define API request/response DTOs for user endpoints
 */

// ============================================================================
// INTERFACES - User List Types
// ============================================================================

/**
 * A paper in the user's saved list.
 * Includes paper details for display.
 */
export interface UserListItem {
  /** UUID identifier for the paper */
  paperUuid: string;
  /** Paper title */
  title: string | null;
  /** Comma-separated author names */
  authors: string | null;
  /** Base64 data URL of thumbnail image */
  thumbnailDataUrl: string | null;
  /** URL slug for the paper page */
  slug: string | null;
  /** When the paper was added to the list */
  createdAt: Date;
}

/**
 * A paper requested by the user for processing.
 * Tracks papers the user wants processed.
 */
export interface UserRequestItem {
  /** arXiv identifier of the requested paper */
  arxivId: string;
  /** Paper title (from arXiv metadata) */
  title: string | null;
  /** Comma-separated author names */
  authors: string | null;
  /** When the request was created */
  createdAt: Date;
  /** Whether the paper has been processed */
  isProcessed: boolean;
  /** Slug of processed paper if available */
  processedSlug: string | null;
}

// ============================================================================
// INTERFACES - API Request/Response DTOs
// ============================================================================

/**
 * Response indicating whether an item exists.
 * Used for checking list/request membership.
 */
export interface ExistsResponse {
  /** Whether the item exists */
  exists: boolean;
}

/**
 * Response indicating whether an item was created.
 * Used for add operations.
 */
export interface CreatedResponse {
  /** Whether the item was created (false if already existed) */
  created: boolean;
}

/**
 * Response indicating whether an item was deleted.
 * Used for remove operations.
 */
export interface DeletedResponse {
  /** Whether the item was deleted (false if didn't exist) */
  deleted: boolean;
}

// ============================================================================
// INTERFACES - Admin Types
// ============================================================================

/**
 * A paper request for admin display.
 * Used by admin endpoints to show all requests across users.
 */
export interface AdminRequestItem {
  /** Internal request ID */
  id: number;
  /** User ID who made the request */
  userId: string;
  /** arXiv identifier of the requested paper */
  arxivId: string;
  /** Paper title (from arXiv metadata) */
  title: string | null;
  /** Comma-separated author names */
  authors: string | null;
  /** When the request was created */
  createdAt: Date;
  /** Whether the paper has been processed */
  isProcessed: boolean;
  /** Slug of processed paper if available */
  processedSlug: string | null;
}

/**
 * Aggregated paper request item for admin display.
 * Groups requests by arXiv ID and shows request counts.
 */
export interface AggregatedRequestItem {
  /** arXiv identifier of the requested paper */
  arxivId: string;
  /** Full arXiv abstract URL */
  arxivAbsUrl: string;
  /** Full arXiv PDF URL */
  arxivPdfUrl: string;
  /** Number of users who requested this paper */
  requestCount: number;
  /** When the first request was made */
  firstRequestedAt: Date;
  /** When the most recent request was made */
  lastRequestedAt: Date;
  /** Paper title (from arXiv metadata) */
  title: string | null;
  /** Comma-separated author names */
  authors: string | null;
  /** Number of pages if known */
  numPages: number | null;
  /** Slug if paper has been processed */
  processedSlug: string | null;
}

/**
 * Response from starting paper processing from a request.
 */
export interface StartProcessingResponse {
  /** UUID of the paper record */
  paperUuid: string;
  /** Current status of the paper */
  status: string;
}

/**
 * Response from deleting a paper request.
 */
export interface DeleteRequestedResponse {
  /** The arXiv ID that was deleted */
  deleted: string;
}
