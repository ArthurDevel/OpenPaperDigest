/**
 * Unit tests for the User List Service (client-side)
 *
 * Tests the client-side API functions for managing user paper lists.
 *
 * Responsibilities:
 * - Test addPaperToUserList makes correct fetch calls
 * - Test isPaperInUserList makes correct fetch calls
 * - Test removePaperFromUserList makes correct fetch calls
 * - Test getMyUserList makes correct fetch calls
 * - Test error handling for all functions
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  addPaperToUserList,
  isPaperInUserList,
  removePaperFromUserList,
  getMyUserList,
} from './users';

// ============================================================================
// TEST SETUP
// ============================================================================

const mockFetch = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal('fetch', mockFetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Creates a mock Response object for fetch.
 */
function createMockResponse(body: unknown, options: { ok: boolean; status?: number }) {
  return {
    ok: options.ok,
    status: options.status ?? (options.ok ? 200 : 500),
    json: vi.fn().mockResolvedValue(body),
    text: vi.fn().mockResolvedValue(typeof body === 'string' ? body : JSON.stringify(body)),
  };
}

// ============================================================================
// addPaperToUserList TESTS
// ============================================================================

describe('addPaperToUserList', () => {
  it('makes POST request to correct URL with credentials', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ created: true }, { ok: true }));

    await addPaperToUserList('paper-uuid-123');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith('/api/users/me/list/paper-uuid-123', {
      method: 'POST',
      credentials: 'include',
    });
  });

  it('returns { created: true } when paper is added successfully', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ created: true }, { ok: true }));

    const result = await addPaperToUserList('paper-uuid-123');

    expect(result).toEqual({ created: true });
  });

  it('returns { created: false } when paper already exists', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ created: false }, { ok: true }));

    const result = await addPaperToUserList('paper-uuid-123');

    expect(result).toEqual({ created: false });
  });

  it('URL-encodes the paper UUID', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ created: true }, { ok: true }));

    await addPaperToUserList('paper/with/slashes');

    expect(mockFetch).toHaveBeenCalledWith('/api/users/me/list/paper%2Fwith%2Fslashes', {
      method: 'POST',
      credentials: 'include',
    });
  });

  it('throws error with response text when request fails', async () => {
    mockFetch.mockResolvedValue(
      createMockResponse('Paper not found', { ok: false, status: 404 })
    );

    await expect(addPaperToUserList('paper-uuid-123')).rejects.toThrow('Paper not found');
  });

  it('throws generic error when request fails with no response text', async () => {
    const mockResponse = {
      ok: false,
      status: 500,
      text: vi.fn().mockResolvedValue(''),
    };
    mockFetch.mockResolvedValue(mockResponse);

    await expect(addPaperToUserList('paper-uuid-123')).rejects.toThrow(
      'Failed to add to list (500)'
    );
  });

  it('throws generic error when text() throws', async () => {
    const mockResponse = {
      ok: false,
      status: 500,
      text: vi.fn().mockRejectedValue(new Error('Text parsing failed')),
    };
    mockFetch.mockResolvedValue(mockResponse);

    await expect(addPaperToUserList('paper-uuid-123')).rejects.toThrow(
      'Failed to add to list (500)'
    );
  });
});

// ============================================================================
// isPaperInUserList TESTS
// ============================================================================

describe('isPaperInUserList', () => {
  it('makes GET request to correct URL with credentials and no-store cache', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ exists: true }, { ok: true }));

    await isPaperInUserList('paper-uuid-123');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith('/api/users/me/list/paper-uuid-123', {
      credentials: 'include',
      cache: 'no-store',
    });
  });

  it('returns true when paper exists in list', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ exists: true }, { ok: true }));

    const result = await isPaperInUserList('paper-uuid-123');

    expect(result).toBe(true);
  });

  it('returns false when paper does not exist in list', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ exists: false }, { ok: true }));

    const result = await isPaperInUserList('paper-uuid-123');

    expect(result).toBe(false);
  });

  it('returns false when request fails (instead of throwing)', async () => {
    mockFetch.mockResolvedValue(createMockResponse({}, { ok: false, status: 500 }));

    const result = await isPaperInUserList('paper-uuid-123');

    expect(result).toBe(false);
  });

  it('returns false when response data is null', async () => {
    mockFetch.mockResolvedValue(createMockResponse(null, { ok: true }));

    const result = await isPaperInUserList('paper-uuid-123');

    expect(result).toBe(false);
  });

  it('URL-encodes the paper UUID', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ exists: true }, { ok: true }));

    await isPaperInUserList('paper/with/slashes');

    expect(mockFetch).toHaveBeenCalledWith('/api/users/me/list/paper%2Fwith%2Fslashes', {
      credentials: 'include',
      cache: 'no-store',
    });
  });
});

// ============================================================================
// removePaperFromUserList TESTS
// ============================================================================

describe('removePaperFromUserList', () => {
  it('makes DELETE request to correct URL with credentials', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ deleted: true }, { ok: true }));

    await removePaperFromUserList('paper-uuid-123');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith('/api/users/me/list/paper-uuid-123', {
      method: 'DELETE',
      credentials: 'include',
    });
  });

  it('returns { deleted: true } when paper is removed successfully', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ deleted: true }, { ok: true }));

    const result = await removePaperFromUserList('paper-uuid-123');

    expect(result).toEqual({ deleted: true });
  });

  it('returns { deleted: false } when paper was not in list', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ deleted: false }, { ok: true }));

    const result = await removePaperFromUserList('paper-uuid-123');

    expect(result).toEqual({ deleted: false });
  });

  it('URL-encodes the paper UUID', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ deleted: true }, { ok: true }));

    await removePaperFromUserList('paper/with/slashes');

    expect(mockFetch).toHaveBeenCalledWith('/api/users/me/list/paper%2Fwith%2Fslashes', {
      method: 'DELETE',
      credentials: 'include',
    });
  });

  it('throws error with response text when request fails', async () => {
    mockFetch.mockResolvedValue(
      createMockResponse('Unauthorized', { ok: false, status: 401 })
    );

    await expect(removePaperFromUserList('paper-uuid-123')).rejects.toThrow('Unauthorized');
  });

  it('throws generic error when request fails with no response text', async () => {
    const mockResponse = {
      ok: false,
      status: 500,
      text: vi.fn().mockResolvedValue(''),
    };
    mockFetch.mockResolvedValue(mockResponse);

    await expect(removePaperFromUserList('paper-uuid-123')).rejects.toThrow(
      'Failed to remove from list (500)'
    );
  });
});

// ============================================================================
// getMyUserList TESTS
// ============================================================================

describe('getMyUserList', () => {
  it('makes GET request to correct URL with credentials and no-store cache', async () => {
    mockFetch.mockResolvedValue(createMockResponse([], { ok: true }));

    await getMyUserList();

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith('/api/users/me/list', {
      credentials: 'include',
      cache: 'no-store',
    });
  });

  it('returns empty array when user has no papers', async () => {
    mockFetch.mockResolvedValue(createMockResponse([], { ok: true }));

    const result = await getMyUserList();

    expect(result).toEqual([]);
  });

  it('returns array of papers when user has papers in list', async () => {
    const mockPapers = [
      {
        paperUuid: 'paper-1',
        title: 'Paper One',
        authors: 'Author A',
        thumbnailDataUrl: 'data:image/png;base64,...',
        slug: 'paper-one',
        createdAt: '2024-01-15T10:00:00Z',
      },
      {
        paperUuid: 'paper-2',
        title: 'Paper Two',
        authors: 'Author B',
        thumbnailDataUrl: null,
        slug: 'paper-two',
        createdAt: '2024-01-16T10:00:00Z',
      },
    ];
    mockFetch.mockResolvedValue(createMockResponse(mockPapers, { ok: true }));

    const result = await getMyUserList();

    expect(result).toEqual(mockPapers);
    expect(result).toHaveLength(2);
  });

  it('throws error with response text when request fails', async () => {
    mockFetch.mockResolvedValue(
      createMockResponse('Unauthorized', { ok: false, status: 401 })
    );

    await expect(getMyUserList()).rejects.toThrow('Unauthorized');
  });

  it('throws generic error when request fails with no response text', async () => {
    const mockResponse = {
      ok: false,
      status: 500,
      text: vi.fn().mockResolvedValue(''),
    };
    mockFetch.mockResolvedValue(mockResponse);

    await expect(getMyUserList()).rejects.toThrow('Failed to fetch list (500)');
  });

  it('throws generic error when text() throws', async () => {
    const mockResponse = {
      ok: false,
      status: 500,
      text: vi.fn().mockRejectedValue(new Error('Text parsing failed')),
    };
    mockFetch.mockResolvedValue(mockResponse);

    await expect(getMyUserList()).rejects.toThrow('Failed to fetch list (500)');
  });
});
