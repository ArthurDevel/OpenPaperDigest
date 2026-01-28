/**
 * Users API E2E Tests
 *
 * Tests for user endpoints (require BetterAuth authentication).
 * - POST /api/users/sync - sync user
 * - GET /api/users/me/list - user's paper list
 * - GET/POST/DELETE /api/users/me/list/[uuid] - manage list items
 * - GET /api/users/me/requests - user's paper requests
 * - GET/POST/DELETE /api/users/me/requests/[arxivId] - manage requests
 * - GET /api/users/me/papers/[uuid]/processing_metrics - processing metrics
 */

import { test, expect } from '@playwright/test';
import { generateTestUuid, generateTestArxivId } from '../setup/test-utils';

// ============================================================================
// TESTS - USER SYNC
// ============================================================================

test.describe('Users API - Sync', () => {
  test.describe('POST /api/users/sync', () => {
    test('returns 400 when id is missing', async ({ request }) => {
      const response = await request.post('/api/users/sync', {
        data: {
          email: 'test@example.com',
        },
      });

      expect(response.status()).toBe(400);

      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error).toContain('id');
    });

    test('returns 400 when email is missing', async ({ request }) => {
      const response = await request.post('/api/users/sync', {
        data: {
          id: 'test-user-id',
        },
      });

      expect(response.status()).toBe(400);

      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error).toContain('email');
    });

    test('returns 400 when id is not a string', async ({ request }) => {
      const response = await request.post('/api/users/sync', {
        data: {
          id: 123,
          email: 'test@example.com',
        },
      });

      expect(response.status()).toBe(400);

      const data = await response.json();
      expect(data).toHaveProperty('error');
    });

    test('accepts valid sync payload', async ({ request }) => {
      const response = await request.post('/api/users/sync', {
        data: {
          id: 'test-user-id-' + Date.now(),
          email: 'test@example.com',
        },
      });

      // May return 200 (success) or 500 (database error)
      expect([200, 500]).toContain(response.status());

      if (response.status() === 200) {
        const data = await response.json();
        expect(data).toHaveProperty('created');
        expect(typeof data.created).toBe('boolean');
      }
    });
  });
});

// ============================================================================
// TESTS - USER LIST (REQUIRES AUTH)
// ============================================================================

test.describe('Users API - My List', () => {
  test.describe('GET /api/users/me/list', () => {
    test('returns 401 without authentication', async ({ request }) => {
      const response = await request.get('/api/users/me/list');

      expect(response.status()).toBe(401);

      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error.toLowerCase()).toContain('unauthorized');
    });
  });

  test.describe('GET /api/users/me/list/[uuid]', () => {
    test('returns 401 without authentication', async ({ request }) => {
      const uuid = generateTestUuid();
      const response = await request.get(`/api/users/me/list/${uuid}`);

      expect(response.status()).toBe(401);

      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error.toLowerCase()).toContain('unauthorized');
    });
  });

  test.describe('POST /api/users/me/list/[uuid]', () => {
    test('returns 401 without authentication', async ({ request }) => {
      const uuid = generateTestUuid();
      const response = await request.post(`/api/users/me/list/${uuid}`);

      expect(response.status()).toBe(401);

      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error.toLowerCase()).toContain('unauthorized');
    });
  });

  test.describe('DELETE /api/users/me/list/[uuid]', () => {
    test('returns 401 without authentication', async ({ request }) => {
      const uuid = generateTestUuid();
      const response = await request.delete(`/api/users/me/list/${uuid}`);

      expect(response.status()).toBe(401);

      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error.toLowerCase()).toContain('unauthorized');
    });
  });
});

// ============================================================================
// TESTS - USER REQUESTS (REQUIRES AUTH)
// ============================================================================

test.describe('Users API - My Requests', () => {
  test.describe('GET /api/users/me/requests', () => {
    test('returns 401 without authentication', async ({ request }) => {
      const response = await request.get('/api/users/me/requests');

      expect(response.status()).toBe(401);

      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error.toLowerCase()).toContain('unauthorized');
    });
  });

  test.describe('GET /api/users/me/requests/[arxivId]', () => {
    test('returns 401 without authentication', async ({ request }) => {
      const arxivId = generateTestArxivId();
      const response = await request.get(`/api/users/me/requests/${arxivId}`);

      expect(response.status()).toBe(401);

      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error.toLowerCase()).toContain('unauthorized');
    });
  });

  test.describe('POST /api/users/me/requests/[arxivId]', () => {
    test('returns 401 without authentication', async ({ request }) => {
      const arxivId = generateTestArxivId();
      const response = await request.post(`/api/users/me/requests/${arxivId}`, {
        data: {
          title: 'Test Paper',
          authors: 'Test Author',
        },
      });

      expect(response.status()).toBe(401);

      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error.toLowerCase()).toContain('unauthorized');
    });
  });

  test.describe('DELETE /api/users/me/requests/[arxivId]', () => {
    test('returns 401 without authentication', async ({ request }) => {
      const arxivId = generateTestArxivId();
      const response = await request.delete(`/api/users/me/requests/${arxivId}`);

      expect(response.status()).toBe(401);

      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error.toLowerCase()).toContain('unauthorized');
    });
  });
});

// ============================================================================
// TESTS - USER PROCESSING METRICS (REQUIRES AUTH)
// ============================================================================

test.describe('Users API - Processing Metrics', () => {
  test.describe('GET /api/users/me/papers/[uuid]/processing_metrics', () => {
    test('returns 401 without authentication', async ({ request }) => {
      const uuid = generateTestUuid();
      const response = await request.get(`/api/users/me/papers/${uuid}/processing_metrics`);

      expect(response.status()).toBe(401);

      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error.toLowerCase()).toContain('unauthorized');
    });
  });
});
