/**
 * Unit tests for the User Requests Service (client-side)
 *
 * Tests the client-side API functions for managing user paper requests.
 *
 * Responsibilities:
 * - Test addUserRequest makes correct fetch calls
 * - Test doesUserRequestExist makes correct fetch calls
 * - Test listMyRequests makes correct fetch calls
 * - Test removeUserRequest makes correct fetch calls
 * - Test error handling for all functions
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  addUserRequest,
  doesUserRequestExist,
  listMyRequests,
  removeUserRequest,
} from './requests';

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
// addUserRequest TESTS
// ============================================================================

describe('addUserRequest', () => {
  it('makes POST request to correct URL with credentials', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ created: true }, { ok: true }));

    await addUserRequest('2401.00001');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith('/api/users/me/requests/2401.00001', {
      method: 'POST',
      credentials: 'include',
    });
  });

  it('returns { created: true } when request is added successfully', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ created: true }, { ok: true }));

    const result = await addUserRequest('2401.00001');

    expect(result).toEqual({ created: true });
  });

  it('returns { created: false } when request already exists', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ created: false }, { ok: true }));

    const result = await addUserRequest('2401.00001');

    expect(result).toEqual({ created: false });
  });

  it('URL-encodes the arXiv ID', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ created: true }, { ok: true }));

    await addUserRequest('cs.AI/0001001');

    expect(mockFetch).toHaveBeenCalledWith('/api/users/me/requests/cs.AI%2F0001001', {
      method: 'POST',
      credentials: 'include',
    });
  });

  it('throws error with response text when request fails', async () => {
    mockFetch.mockResolvedValue(
      createMockResponse('Invalid arXiv ID format', { ok: false, status: 400 })
    );

    await expect(addUserRequest('invalid')).rejects.toThrow('Invalid arXiv ID format');
  });

  it('throws generic error when request fails with no response text', async () => {
    const mockResponse = {
      ok: false,
      status: 500,
      text: vi.fn().mockResolvedValue(''),
    };
    mockFetch.mockResolvedValue(mockResponse);

    await expect(addUserRequest('2401.00001')).rejects.toThrow('Failed to add request (500)');
  });

  it('throws generic error when text() throws', async () => {
    const mockResponse = {
      ok: false,
      status: 500,
      text: vi.fn().mockRejectedValue(new Error('Text parsing failed')),
    };
    mockFetch.mockResolvedValue(mockResponse);

    await expect(addUserRequest('2401.00001')).rejects.toThrow('Failed to add request (500)');
  });
});

// ============================================================================
// doesUserRequestExist TESTS
// ============================================================================

describe('doesUserRequestExist', () => {
  it('makes GET request to correct URL with credentials and no-store cache', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ exists: true }, { ok: true }));

    await doesUserRequestExist('2401.00001');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith('/api/users/me/requests/2401.00001', {
      credentials: 'include',
      cache: 'no-store',
    });
  });

  it('returns true when request exists', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ exists: true }, { ok: true }));

    const result = await doesUserRequestExist('2401.00001');

    expect(result).toBe(true);
  });

  it('returns false when request does not exist', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ exists: false }, { ok: true }));

    const result = await doesUserRequestExist('2401.00001');

    expect(result).toBe(false);
  });

  it('returns false when API request fails (instead of throwing)', async () => {
    mockFetch.mockResolvedValue(createMockResponse({}, { ok: false, status: 500 }));

    const result = await doesUserRequestExist('2401.00001');

    expect(result).toBe(false);
  });

  it('returns false when response data is null', async () => {
    mockFetch.mockResolvedValue(createMockResponse(null, { ok: true }));

    const result = await doesUserRequestExist('2401.00001');

    expect(result).toBe(false);
  });

  it('URL-encodes the arXiv ID', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ exists: true }, { ok: true }));

    await doesUserRequestExist('cs.AI/0001001');

    expect(mockFetch).toHaveBeenCalledWith('/api/users/me/requests/cs.AI%2F0001001', {
      credentials: 'include',
      cache: 'no-store',
    });
  });
});

// ============================================================================
// listMyRequests TESTS
// ============================================================================

describe('listMyRequests', () => {
  it('makes GET request to correct URL with credentials and no-store cache', async () => {
    mockFetch.mockResolvedValue(createMockResponse([], { ok: true }));

    await listMyRequests();

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith('/api/users/me/requests', {
      credentials: 'include',
      cache: 'no-store',
    });
  });

  it('returns empty array when user has no requests', async () => {
    mockFetch.mockResolvedValue(createMockResponse([], { ok: true }));

    const result = await listMyRequests();

    expect(result).toEqual([]);
  });

  it('returns array of requests when user has requests', async () => {
    const mockRequests = [
      {
        arxivId: '2401.00001',
        title: 'Paper One',
        authors: 'Author A',
        isProcessed: false,
        processedSlug: null,
        createdAt: '2024-01-15T10:00:00Z',
      },
      {
        arxivId: '2401.00002',
        title: 'Paper Two',
        authors: 'Author B',
        isProcessed: true,
        processedSlug: 'paper-two',
        createdAt: '2024-01-16T10:00:00Z',
      },
    ];
    mockFetch.mockResolvedValue(createMockResponse(mockRequests, { ok: true }));

    const result = await listMyRequests();

    expect(result).toEqual(mockRequests);
    expect(result).toHaveLength(2);
  });

  it('throws error with response text when request fails', async () => {
    mockFetch.mockResolvedValue(
      createMockResponse('Unauthorized', { ok: false, status: 401 })
    );

    await expect(listMyRequests()).rejects.toThrow('Unauthorized');
  });

  it('throws generic error when request fails with no response text', async () => {
    const mockResponse = {
      ok: false,
      status: 500,
      text: vi.fn().mockResolvedValue(''),
    };
    mockFetch.mockResolvedValue(mockResponse);

    await expect(listMyRequests()).rejects.toThrow('Failed to fetch requests (500)');
  });

  it('throws generic error when text() throws', async () => {
    const mockResponse = {
      ok: false,
      status: 500,
      text: vi.fn().mockRejectedValue(new Error('Text parsing failed')),
    };
    mockFetch.mockResolvedValue(mockResponse);

    await expect(listMyRequests()).rejects.toThrow('Failed to fetch requests (500)');
  });
});

// ============================================================================
// removeUserRequest TESTS
// ============================================================================

describe('removeUserRequest', () => {
  it('makes DELETE request to correct URL with credentials', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ deleted: true }, { ok: true }));

    await removeUserRequest('2401.00001');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith('/api/users/me/requests/2401.00001', {
      method: 'DELETE',
      credentials: 'include',
    });
  });

  it('returns { deleted: true } when request is removed successfully', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ deleted: true }, { ok: true }));

    const result = await removeUserRequest('2401.00001');

    expect(result).toEqual({ deleted: true });
  });

  it('returns { deleted: false } when request was not found', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ deleted: false }, { ok: true }));

    const result = await removeUserRequest('2401.00001');

    expect(result).toEqual({ deleted: false });
  });

  it('URL-encodes the arXiv ID', async () => {
    mockFetch.mockResolvedValue(createMockResponse({ deleted: true }, { ok: true }));

    await removeUserRequest('cs.AI/0001001');

    expect(mockFetch).toHaveBeenCalledWith('/api/users/me/requests/cs.AI%2F0001001', {
      method: 'DELETE',
      credentials: 'include',
    });
  });

  it('throws error with response text when request fails', async () => {
    mockFetch.mockResolvedValue(
      createMockResponse('Unauthorized', { ok: false, status: 401 })
    );

    await expect(removeUserRequest('2401.00001')).rejects.toThrow('Unauthorized');
  });

  it('throws generic error when request fails with no response text', async () => {
    const mockResponse = {
      ok: false,
      status: 500,
      text: vi.fn().mockResolvedValue(''),
    };
    mockFetch.mockResolvedValue(mockResponse);

    await expect(removeUserRequest('2401.00001')).rejects.toThrow(
      'Failed to remove request (500)'
    );
  });

  it('throws generic error when text() throws', async () => {
    const mockResponse = {
      ok: false,
      status: 500,
      text: vi.fn().mockRejectedValue(new Error('Text parsing failed')),
    };
    mockFetch.mockResolvedValue(mockResponse);

    await expect(removeUserRequest('2401.00001')).rejects.toThrow(
      'Failed to remove request (500)'
    );
  });
});
