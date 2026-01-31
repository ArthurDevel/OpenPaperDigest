/**
 * User List Service
 *
 * Client-side service for managing user paper lists via API calls.
 *
 * Responsibilities:
 * - Add papers to user's reading list
 * - Check if paper is in user's list
 * - Remove papers from user's list
 * - Fetch user's complete paper list
 */

// ============================================================================
// TYPES
// ============================================================================

export type CreatedResponse = { created: boolean };
export type ExistsResponse = { exists: boolean };

export type UserListItem = {
  paperUuid: string;
  title?: string | null;
  authors?: string | null;
  thumbnailDataUrl?: string | null;
  slug?: string | null;
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
 * Add a paper to the user's reading list.
 * @param paperUuid - UUID of the paper to add
 * @returns Response indicating if the paper was created
 */
export async function addPaperToUserList(paperUuid: string): Promise<CreatedResponse> {
  const resp = await fetch(`${API_BASE}/users/me/list/${encodeURIComponent(paperUuid)}`, {
    method: 'POST',
    credentials: 'include',
  });
  if (!resp.ok) {
    const txt = await resp.text().catch(() => '');
    throw new Error(txt || `Failed to add to list (${resp.status})`);
  }
  return resp.json();
}

/**
 * Check if a paper is in the user's reading list.
 * @param paperUuid - UUID of the paper to check
 * @returns True if paper is in user's list
 */
export async function isPaperInUserList(paperUuid: string): Promise<boolean> {
  const resp = await fetch(`${API_BASE}/users/me/list/${encodeURIComponent(paperUuid)}`, {
    credentials: 'include',
    cache: 'no-store' as RequestCache,
  });
  if (!resp.ok) return false;
  const data: ExistsResponse = await resp.json();
  return Boolean(data?.exists);
}

/**
 * Remove a paper from the user's reading list.
 * @param paperUuid - UUID of the paper to remove
 * @returns Response indicating if the paper was deleted
 */
export async function removePaperFromUserList(paperUuid: string): Promise<{ deleted: boolean }> {
  const resp = await fetch(`${API_BASE}/users/me/list/${encodeURIComponent(paperUuid)}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  if (!resp.ok) {
    const txt = await resp.text().catch(() => '');
    throw new Error(txt || `Failed to remove from list (${resp.status})`);
  }
  return resp.json();
}

/**
 * Get the user's complete paper reading list.
 * @returns Array of papers in user's list
 */
export async function getMyUserList(): Promise<UserListItem[]> {
  const resp = await fetch(`${API_BASE}/users/me/list`, {
    credentials: 'include',
    cache: 'no-store' as RequestCache,
  });
  if (!resp.ok) {
    const txt = await resp.text().catch(() => '');
    throw new Error(txt || `Failed to fetch list (${resp.status})`);
  }
  return resp.json();
}
