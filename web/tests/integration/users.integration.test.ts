/**
 * Users API Integration Tests
 *
 * Tests for user endpoints using mocked database and auth.
 * - POST /api/users/sync - sync user
 * - GET /api/users/me/list - user's paper list
 * - GET/POST/DELETE /api/users/me/list/[uuid] - manage list items
 * - GET /api/users/me/requests - user's paper requests
 * - GET/POST/DELETE /api/users/me/requests/[arxivId] - manage requests
 * - GET /api/users/me/papers/[uuid]/processing_metrics - processing metrics
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { testApiHandler } from 'next-test-api-route-handler';
import {
  resetAllMocks,
  mockAuthenticatedSession,
  defaultMockSession,
  generateTestUuid,
  generateTestArxivId,
  mockQueryReturns,
  mockOrderReturns,
} from './setup';

// ============================================================================
// TESTS - USER LIST (REQUIRES AUTH)
// ============================================================================

describe('Users API - My List', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('GET /api/users/me/list', () => {
    it('returns 401 without authentication', async () => {
      const appHandler = await import('@/app/api/users/me/list/route');

      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(401);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error.toLowerCase()).toContain('unauthorized');
        },
      });
    });

    it('returns list when authenticated', async () => {
      mockAuthenticatedSession();
      // Mock user_lists query with joined papers
      mockOrderReturns([
        {
          created_at: new Date().toISOString(),
          papers: {
            paper_uuid: generateTestUuid(),
            title: 'Test Paper',
            authors: 'Test Author',
            thumbnail_data_url: null,
          },
        },
      ]);
      // Mock slugs query
      mockOrderReturns([]);

      const appHandler = await import('@/app/api/users/me/list/route');

      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(Array.isArray(data)).toBe(true);
        },
      });
    });
  });

  describe('GET /api/users/me/list/[uuid]', () => {
    it('returns 401 without authentication', async () => {
      const appHandler = await import('@/app/api/users/me/list/[uuid]/route');
      const uuid = generateTestUuid();

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(401);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error.toLowerCase()).toContain('unauthorized');
        },
      });
    });

    it('checks if paper is in list when authenticated', async () => {
      mockAuthenticatedSession();
      // Mock paper lookup
      mockQueryReturns({ id: 1 });
      // Mock userList lookup
      mockQueryReturns({
        user_id: defaultMockSession.user.id,
        paper_id: 1,
      });

      const appHandler = await import('@/app/api/users/me/list/[uuid]/route');
      const uuid = generateTestUuid();

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data).toHaveProperty('exists');
        },
      });
    });
  });

  describe('POST /api/users/me/list/[uuid]', () => {
    it('returns 401 without authentication', async () => {
      const appHandler = await import('@/app/api/users/me/list/[uuid]/route');
      const uuid = generateTestUuid();

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'POST' });

          expect(response.status).toBe(401);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error.toLowerCase()).toContain('unauthorized');
        },
      });
    });

    it('adds paper to list when authenticated', async () => {
      mockAuthenticatedSession();
      // Mock paper lookup
      mockQueryReturns({ id: 1, paper_uuid: generateTestUuid() });
      // Mock existing list check (not found)
      mockQueryReturns(null);
      // Insert succeeds (no return needed for insert without select)

      const appHandler = await import('@/app/api/users/me/list/[uuid]/route');
      const uuid = generateTestUuid();

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'POST' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data).toHaveProperty('created');
        },
      });
    });
  });

  describe('DELETE /api/users/me/list/[uuid]', () => {
    it('returns 401 without authentication', async () => {
      const appHandler = await import('@/app/api/users/me/list/[uuid]/route');
      const uuid = generateTestUuid();

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'DELETE' });

          expect(response.status).toBe(401);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error.toLowerCase()).toContain('unauthorized');
        },
      });
    });

    it('removes paper from list when authenticated', async () => {
      mockAuthenticatedSession();
      // Mock paper lookup
      mockQueryReturns({ id: 1 });
      // Mock existing list check (found)
      mockQueryReturns({ id: 1 });
      // Delete succeeds

      const appHandler = await import('@/app/api/users/me/list/[uuid]/route');
      const uuid = generateTestUuid();

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'DELETE' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data).toHaveProperty('deleted');
        },
      });
    });
  });
});

// ============================================================================
// TESTS - USER REQUESTS (REQUIRES AUTH)
// ============================================================================

describe('Users API - My Requests', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('GET /api/users/me/requests', () => {
    it('returns 401 without authentication', async () => {
      const appHandler = await import('@/app/api/users/me/requests/route');

      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(401);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error.toLowerCase()).toContain('unauthorized');
        },
      });
    });

    it('returns requests when authenticated', async () => {
      mockAuthenticatedSession();
      mockOrderReturns([]);

      const appHandler = await import('@/app/api/users/me/requests/route');

      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(Array.isArray(data)).toBe(true);
        },
      });
    });
  });

  describe('GET /api/users/me/requests/[arxivId]', () => {
    it('returns 401 without authentication', async () => {
      const appHandler = await import('@/app/api/users/me/requests/[arxivId]/route');
      const arxivId = generateTestArxivId();

      await testApiHandler({
        appHandler,
        params: { arxivId },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(401);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error.toLowerCase()).toContain('unauthorized');
        },
      });
    });
  });

  describe('POST /api/users/me/requests/[arxivId]', () => {
    it('returns 401 without authentication', async () => {
      const appHandler = await import('@/app/api/users/me/requests/[arxivId]/route');
      const arxivId = generateTestArxivId();

      await testApiHandler({
        appHandler,
        params: { arxivId },
        test: async ({ fetch }) => {
          const response = await fetch({
            method: 'POST',
            body: JSON.stringify({ title: 'Test Paper', authors: 'Test Author' }),
            headers: { 'Content-Type': 'application/json' },
          });

          expect(response.status).toBe(401);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error.toLowerCase()).toContain('unauthorized');
        },
      });
    });
  });

  describe('DELETE /api/users/me/requests/[arxivId]', () => {
    it('returns 401 without authentication', async () => {
      const appHandler = await import('@/app/api/users/me/requests/[arxivId]/route');
      const arxivId = generateTestArxivId();

      await testApiHandler({
        appHandler,
        params: { arxivId },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'DELETE' });

          expect(response.status).toBe(401);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error.toLowerCase()).toContain('unauthorized');
        },
      });
    });
  });
});

// ============================================================================
// TESTS - USER PROCESSING METRICS (REQUIRES AUTH)
// ============================================================================

describe('Users API - Processing Metrics', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('GET /api/users/me/papers/[uuid]/processing_metrics', () => {
    it('returns 401 without authentication', async () => {
      const appHandler = await import(
        '@/app/api/users/me/papers/[uuid]/processing_metrics/route'
      );
      const uuid = generateTestUuid();

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(401);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error.toLowerCase()).toContain('unauthorized');
        },
      });
    });

    it('returns metrics when authenticated', async () => {
      mockAuthenticatedSession();
      // Paper must have initiated_by_user_id matching the session user
      mockQueryReturns({
        paper_uuid: generateTestUuid(),
        status: 'completed',
        num_pages: 10,
        processing_time_seconds: 120,
        total_cost: 0.05,
        avg_cost_per_page: 0.005,
        started_at: new Date().toISOString(),
        finished_at: new Date().toISOString(),
        error_message: null,
        initiated_by_user_id: defaultMockSession.user.id,
      });

      const appHandler = await import(
        '@/app/api/users/me/papers/[uuid]/processing_metrics/route'
      );
      const uuid = generateTestUuid();

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data).toHaveProperty('status');
        },
      });
    });
  });
});
