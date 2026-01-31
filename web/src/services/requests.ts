/**
 * User Requests Service
 *
 * Client-side service for managing user paper requests via API calls.
 *
 * Responsibilities:
 * - Add paper processing requests
 * - Check if request exists
 * - Remove paper requests
 * - List user's paper requests
 */

// ============================================================================
// TYPES
// ============================================================================

export type CreatedResponse = { created: boolean };
export type ExistsResponse = { exists: boolean };

export type UserRequestItem = {
  arxivId: string;
  title?: string | null;
  authors?: string | null;
  isProcessed?: boolean;
  processedSlug?: string | null;
  createdAt?: string | null;
};

// ============================================================================
// CONSTANTS
// ============================================================================

const API_BASE = '/api';

// ============================================================================
// API FUNCTIONS
// ============================================================================

/**
 * Add a paper processing request for an arXiv paper.
 * @param arxivId - arXiv ID to request
 * @returns Response indicating if the request was created
 */
export async function addUserRequest(arxivId: string): Promise<CreatedResponse> {
  const resp = await fetch(`${API_BASE}/users/me/requests/${encodeURIComponent(arxivId)}`, {
    method: 'POST',
    credentials: 'include',
  });
  if (!resp.ok) {
    const txt = await resp.text().catch(() => '');
    throw new Error(txt || `Failed to add request (${resp.status})`);
  }
  return resp.json();
}

/**
 * Check if a paper request exists for the user.
 * @param arxivId - arXiv ID to check
 * @returns True if request exists
 */
export async function doesUserRequestExist(arxivId: string): Promise<boolean> {
  const resp = await fetch(`${API_BASE}/users/me/requests/${encodeURIComponent(arxivId)}`, {
    credentials: 'include',
    cache: 'no-store' as RequestCache,
  });
  if (!resp.ok) return false;
  const data: ExistsResponse = await resp.json();
  return Boolean(data?.exists);
}

/**
 * List all paper requests for the user.
 * @returns Array of user's paper requests
 */
export async function listMyRequests(): Promise<UserRequestItem[]> {
  const resp = await fetch(`${API_BASE}/users/me/requests`, {
    credentials: 'include',
    cache: 'no-store' as RequestCache,
  });
  if (!resp.ok) {
    const txt = await resp.text().catch(() => '');
    throw new Error(txt || `Failed to fetch requests (${resp.status})`);
  }
  return resp.json();
}

/**
 * Remove a paper request for the user.
 * @param arxivId - arXiv ID to remove
 * @returns Response indicating if the request was deleted
 */
export async function removeUserRequest(arxivId: string): Promise<{ deleted: boolean }> {
  const resp = await fetch(`${API_BASE}/users/me/requests/${encodeURIComponent(arxivId)}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  if (!resp.ok) {
    const txt = await resp.text().catch(() => '');
    throw new Error(txt || `Failed to remove request (${resp.status})`);
  }
  return resp.json();
}
