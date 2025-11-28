/**
 * Utility functions for managing last visit timestamp in localStorage.
 * Used to track when a user last visited the site to show "new papers" banner.
 */

const STORAGE_KEY = 'ps_last_visit';

/**
 * Gets the last visit timestamp from localStorage.
 * @returns ISO timestamp string if found, null otherwise
 */
export function getLastVisitTimestamp(): string | null {
  try {
    if (typeof window === 'undefined') {
      return null;
    }
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

/**
 * Sets the last visit timestamp in localStorage to the current time.
 * @returns true if successful, false otherwise
 */
export function setLastVisitTimestamp(): boolean {
  try {
    if (typeof window === 'undefined') {
      return false;
    }
    const now = new Date().toISOString();
    localStorage.setItem(STORAGE_KEY, now);
    return true;
  } catch {
    return false;
  }
}

