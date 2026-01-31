/**
 * Shared API type definitions for the Paper Summarizer application.
 *
 * Responsibilities:
 * - Define common API error response types
 * - Define standard response wrapper types
 * - Define shared utility types for API endpoints
 */

// ============================================================================
// INTERFACES - Error Responses
// ============================================================================

/**
 * Standard API error response structure.
 * Used for all error responses across the application.
 */
export interface ApiError {
  /** Error message describing what went wrong */
  error: string;
  /** Optional error code for programmatic handling */
  code?: string;
  /** Optional additional details about the error */
  details?: Record<string, unknown>;
}

/**
 * Validation error response with field-level details.
 * Used when request validation fails.
 */
export interface ValidationError {
  /** General error message */
  error: string;
  /** Validation code */
  code: 'VALIDATION_ERROR';
  /** Field-level error messages */
  fieldErrors: Record<string, string[]>;
}

// ============================================================================
// INTERFACES - Success Responses
// ============================================================================

/**
 * Generic success response with a message.
 * Used for operations that don't return data.
 */
export interface SuccessResponse {
  /** Success indicator */
  success: true;
  /** Optional message describing the result */
  message?: string;
}

/**
 * Count response for aggregate queries.
 * Used by count endpoints.
 */
export interface CountResponse {
  /** The count value */
  count: number;
}

// ============================================================================
// INTERFACES - Pagination
// ============================================================================

/**
 * Pagination parameters for list endpoints.
 */
export interface PaginationParams {
  /** Page number (1-indexed) */
  page?: number;
  /** Items per page */
  limit?: number;
}

/**
 * Pagination metadata included in paginated responses.
 */
export interface PaginationMeta {
  /** Total number of items */
  total: number;
  /** Current page number */
  page: number;
  /** Items per page */
  limit: number;
  /** Whether more pages exist */
  hasMore: boolean;
}

// ============================================================================
// TYPE UTILITIES
// ============================================================================

/**
 * Makes specified keys of T required.
 * Useful for creating stricter versions of optional types.
 */
export type RequireKeys<T, K extends keyof T> = T & Required<Pick<T, K>>;

/**
 * API response that is either success data or an error.
 * Use for type-safe response handling.
 */
export type ApiResponse<T> = T | ApiError;
