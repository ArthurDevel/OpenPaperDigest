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
  prismaMock,
  authMock,
  resetAllMocks,
  mockAuthenticatedSession,
  defaultMockSession,
  generateTestUuid,
  generateTestArxivId,
} from './setup';

// ============================================================================
// TESTS - USER SYNC
// ============================================================================

describe('Users API - Sync', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('POST /api/users/sync', () => {
    it('returns 400 when id is missing', async () => {
      const appHandler = await import('@/app/api/users/sync/route');

      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({
            method: 'POST',
            body: JSON.stringify({ email: 'test@example.com' }),
            headers: { 'Content-Type': 'application/json' },
          });

          expect(response.status).toBe(400);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error.toLowerCase()).toContain('id');
        },
      });
    });

    it('returns 400 when email is missing', async () => {
      const appHandler = await import('@/app/api/users/sync/route');

      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({
            method: 'POST',
            body: JSON.stringify({ id: 'test-user-id' }),
            headers: { 'Content-Type': 'application/json' },
          });

          expect(response.status).toBe(400);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error.toLowerCase()).toContain('email');
        },
      });
    });

    it('returns 400 when id is not a string', async () => {
      const appHandler = await import('@/app/api/users/sync/route');

      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({
            method: 'POST',
            body: JSON.stringify({ id: 123, email: 'test@example.com' }),
            headers: { 'Content-Type': 'application/json' },
          });

          expect(response.status).toBe(400);

          const data = await response.json();
          expect(data).toHaveProperty('error');
        },
      });
    });

    it('syncs user with valid payload', async () => {
      prismaMock.user.upsert.mockResolvedValue({
        id: 'test-user-id',
        email: 'test@example.com',
        createdAt: new Date(),
      });

      const appHandler = await import('@/app/api/users/sync/route');

      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({
            method: 'POST',
            body: JSON.stringify({
              id: 'test-user-id-' + Date.now(),
              email: 'test@example.com',
            }),
            headers: { 'Content-Type': 'application/json' },
          });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data).toHaveProperty('created');
          expect(typeof data.created).toBe('boolean');
        },
      });
    });
  });
});

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
      prismaMock.userList.findMany.mockResolvedValue([
        {
          createdAt: new Date(),
          paper: {
            paperUuid: generateTestUuid(),
            title: 'Test Paper',
            authors: 'Test Author',
            thumbnailDataUrl: null,
            slugs: [],
          },
        },
      ]);

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
      prismaMock.paper.findUnique.mockResolvedValue({ id: 1 });
      // Mock userList lookup
      prismaMock.userList.findUnique.mockResolvedValue({
        userId: defaultMockSession.user.id,
        paperId: 1,
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
      prismaMock.user.findUnique.mockResolvedValue({ id: defaultMockSession.user.id });
      prismaMock.paper.findUnique.mockResolvedValue({ id: 1, paperUuid: generateTestUuid() });
      prismaMock.userList.findUnique.mockResolvedValue(null);
      prismaMock.userList.create.mockResolvedValue({
        userId: defaultMockSession.user.id,
        paperId: 1,
      });

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
      prismaMock.paper.findUnique.mockResolvedValue({ id: 1 });
      prismaMock.userList.deleteMany.mockResolvedValue({ count: 1 });

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
      prismaMock.userRequest.findMany.mockResolvedValue([]);

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
      // Paper must have initiatedByUserId matching the session user
      prismaMock.paper.findUnique.mockResolvedValue({
        paperUuid: generateTestUuid(),
        status: 'completed',
        numPages: 10,
        processingTimeSeconds: 120,
        totalCost: 0.05,
        avgCostPerPage: 0.005,
        startedAt: new Date(),
        finishedAt: new Date(),
        errorMessage: null,
        initiatedByUserId: defaultMockSession.user.id,
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
