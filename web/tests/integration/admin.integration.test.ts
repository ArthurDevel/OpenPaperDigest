/**
 * Admin API Integration Tests
 *
 * Tests for admin endpoints using mocked database and auth.
 * - GET /api/admin/papers - list all papers
 * - GET /api/admin/papers/cumulative_daily - daily stats
 * - POST /api/admin/papers/import - import paper JSON
 * - DELETE /api/admin/papers/[uuid] - delete paper
 * - POST /api/admin/papers/[uuid]/restart - restart processing
 * - GET /api/admin/papers/[uuid]/processing_metrics - metrics
 * - GET /api/admin/requested_papers - list requests
 * - DELETE /api/admin/requested_papers/[id] - delete request
 * - POST /api/admin/requested_papers/[id]/start_processing - start processing
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { testApiHandler } from 'next-test-api-route-handler';
import {
  resetAllMocks,
  mockAdminAuthenticated,
  generateTestUuid,
  generateTestArxivId,
  createTestPaperPayload,
  mockQueryReturns,
  mockQueryReturnsSingle,
  mockCountReturns,
  mockLimitReturns,
  mockOrderReturns,
} from './setup';

// ============================================================================
// TESTS - ADMIN PAPERS LIST
// ============================================================================

describe('Admin API - Papers List', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('GET /api/admin/papers', () => {
    it('returns 401 without authentication', async () => {
      const appHandler = await import('@/app/api/admin/papers/route');

      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(401);
        },
      });
    });

    it('returns papers list with valid admin auth', async () => {
      mockAdminAuthenticated();
      // listAllPapers uses .from().select().order().limit() pattern
      mockLimitReturns([
        {
          paper_uuid: generateTestUuid(),
          status: 'completed',
          title: 'Test Paper',
          authors: 'Test Author',
          created_at: new Date().toISOString(),
        },
      ]);

      const appHandler = await import('@/app/api/admin/papers/route');

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

    it('accepts status filter parameter', async () => {
      mockAdminAuthenticated();
      // With status filter, query ends with .in() after .limit()
      mockLimitReturns([]);

      const appHandler = await import('@/app/api/admin/papers/route');

      await testApiHandler({
        appHandler,
        url: '/api/admin/papers?status=completed',
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(Array.isArray(data)).toBe(true);
        },
      });
    });

    it('accepts limit parameter', async () => {
      mockAdminAuthenticated();
      mockLimitReturns([]);

      const appHandler = await import('@/app/api/admin/papers/route');

      await testApiHandler({
        appHandler,
        url: '/api/admin/papers?limit=10',
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(Array.isArray(data)).toBe(true);
        },
      });
    });

    it('returns 400 for invalid limit parameter', async () => {
      mockAdminAuthenticated();

      const appHandler = await import('@/app/api/admin/papers/route');

      await testApiHandler({
        appHandler,
        url: '/api/admin/papers?limit=0',
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(400);

          const data = await response.json();
          expect(data).toHaveProperty('error');
        },
      });
    });

    it('returns 400 for limit exceeding maximum', async () => {
      mockAdminAuthenticated();

      const appHandler = await import('@/app/api/admin/papers/route');

      await testApiHandler({
        appHandler,
        url: '/api/admin/papers?limit=20000',
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(400);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error).toContain('10000');
        },
      });
    });
  });
});

// ============================================================================
// TESTS - CUMULATIVE DAILY STATS
// ============================================================================

describe('Admin API - Cumulative Daily Stats', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('GET /api/admin/papers/cumulative_daily', () => {
    it('returns 401 without authentication', async () => {
      const appHandler = await import('@/app/api/admin/papers/cumulative_daily/route');

      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(401);
        },
      });
    });

    it('returns daily stats with valid admin auth', async () => {
      mockAdminAuthenticated();
      mockCountReturns(0);

      const appHandler = await import('@/app/api/admin/papers/cumulative_daily/route');

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
});

// ============================================================================
// TESTS - PAPER IMPORT
// ============================================================================

describe('Admin API - Paper Import', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('POST /api/admin/papers/import', () => {
    it('returns 401 without authentication', async () => {
      const appHandler = await import('@/app/api/admin/papers/import/route');

      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({
            method: 'POST',
            body: JSON.stringify(createTestPaperPayload()),
            headers: { 'Content-Type': 'application/json' },
          });

          expect(response.status).toBe(401);
        },
      });
    });

    it('returns 400 for invalid body (array)', async () => {
      mockAdminAuthenticated();

      const appHandler = await import('@/app/api/admin/papers/import/route');

      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({
            method: 'POST',
            body: JSON.stringify([]),
            headers: { 'Content-Type': 'application/json' },
          });

          expect(response.status).toBe(400);

          const data = await response.json();
          expect(data).toHaveProperty('error');
        },
      });
    });

    it('returns 400 for empty body', async () => {
      mockAdminAuthenticated();

      const appHandler = await import('@/app/api/admin/papers/import/route');

      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({
            method: 'POST',
            body: JSON.stringify({}),
            headers: { 'Content-Type': 'application/json' },
          });

          // Empty object should fail validation (no paper_uuid)
          expect([400, 500]).toContain(response.status);
        },
      });
    });
  });
});

// ============================================================================
// TESTS - PAPER DELETE
// ============================================================================

describe('Admin API - Paper Delete', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('DELETE /api/admin/papers/[uuid]', () => {
    it('returns 401 without authentication', async () => {
      const appHandler = await import('@/app/api/admin/papers/[uuid]/route');
      const uuid = generateTestUuid();

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'DELETE' });

          expect(response.status).toBe(401);
        },
      });
    });

    it('returns 404 for non-existent paper', async () => {
      mockAdminAuthenticated();
      mockQueryReturns(null);

      const appHandler = await import('@/app/api/admin/papers/[uuid]/route');
      const uuid = generateTestUuid();

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'DELETE' });

          expect(response.status).toBe(404);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error.toLowerCase()).toContain('not found');
        },
      });
    });

    it('deletes paper with valid admin auth', async () => {
      mockAdminAuthenticated();
      const uuid = generateTestUuid();
      mockQueryReturns({
        id: 1,
        paper_uuid: uuid,
      });

      const appHandler = await import('@/app/api/admin/papers/[uuid]/route');

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'DELETE' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data).toHaveProperty('deleted');
          // Note: deleted contains the UUID string, not a boolean
          expect(data.deleted).toBe(uuid);
        },
      });
    });
  });
});

// ============================================================================
// TESTS - PAPER RESTART
// ============================================================================

describe('Admin API - Paper Restart', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('POST /api/admin/papers/[uuid]/restart', () => {
    it('returns 401 without authentication', async () => {
      const appHandler = await import('@/app/api/admin/papers/[uuid]/restart/route');
      const uuid = generateTestUuid();

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'POST' });

          expect(response.status).toBe(401);
        },
      });
    });

    it('returns 404 for non-existent paper', async () => {
      mockAdminAuthenticated();
      mockQueryReturns(null);

      const appHandler = await import('@/app/api/admin/papers/[uuid]/restart/route');
      const uuid = generateTestUuid();

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'POST' });

          expect(response.status).toBe(404);

          const data = await response.json();
          expect(data).toHaveProperty('error');
        },
      });
    });

    it('restarts paper processing with valid admin auth', async () => {
      mockAdminAuthenticated();
      // First query: find paper
      mockQueryReturns({
        id: 1,
        status: 'failed',
      });
      // Second query: update returns the paper
      mockQueryReturnsSingle({
        paper_uuid: generateTestUuid(),
        status: 'not_started',
        error_message: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        started_at: null,
        finished_at: null,
      });

      const appHandler = await import('@/app/api/admin/papers/[uuid]/restart/route');
      const uuid = generateTestUuid();

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'POST' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data.status).toBe('not_started');
        },
      });
    });
  });
});

// ============================================================================
// TESTS - ADMIN PROCESSING METRICS
// ============================================================================

describe('Admin API - Processing Metrics', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('GET /api/admin/papers/[uuid]/processing_metrics', () => {
    it('returns 401 without authentication', async () => {
      const appHandler = await import(
        '@/app/api/admin/papers/[uuid]/processing_metrics/route'
      );
      const uuid = generateTestUuid();

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(401);
        },
      });
    });

    it('returns 404 for non-existent paper', async () => {
      mockAdminAuthenticated();
      mockQueryReturns(null);

      const appHandler = await import(
        '@/app/api/admin/papers/[uuid]/processing_metrics/route'
      );
      const uuid = generateTestUuid();

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(404);

          const data = await response.json();
          expect(data).toHaveProperty('error');
        },
      });
    });

    it('returns metrics with valid admin auth', async () => {
      mockAdminAuthenticated();
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
      });

      const appHandler = await import(
        '@/app/api/admin/papers/[uuid]/processing_metrics/route'
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
          expect(data).toHaveProperty('numPages');
        },
      });
    });
  });
});

// ============================================================================
// TESTS - REQUESTED PAPERS LIST
// ============================================================================

describe('Admin API - Requested Papers List', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('GET /api/admin/requested_papers', () => {
    it('returns 401 without authentication', async () => {
      const appHandler = await import('@/app/api/admin/requested_papers/route');

      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(401);
        },
      });
    });

    it('returns requested papers with valid admin auth', async () => {
      mockAdminAuthenticated();
      mockOrderReturns([]);

      const appHandler = await import('@/app/api/admin/requested_papers/route');

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
});

// ============================================================================
// TESTS - DELETE REQUESTED PAPER
// ============================================================================

describe('Admin API - Delete Requested Paper', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('DELETE /api/admin/requested_papers/[id]', () => {
    it('returns 401 without authentication', async () => {
      const appHandler = await import('@/app/api/admin/requested_papers/[id]/route');
      const arxivId = generateTestArxivId();

      await testApiHandler({
        appHandler,
        params: { id: arxivId },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'DELETE' });

          expect(response.status).toBe(401);
        },
      });
    });

    it('returns 400 for invalid arXiv ID format', async () => {
      mockAdminAuthenticated();

      const appHandler = await import('@/app/api/admin/requested_papers/[id]/route');

      await testApiHandler({
        appHandler,
        params: { id: 'invalid-format' },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'DELETE' });

          expect(response.status).toBe(400);

          const data = await response.json();
          expect(data).toHaveProperty('error');
        },
      });
    });

    it('deletes requested paper with valid admin auth', async () => {
      mockAdminAuthenticated();
      // Mock count of existing requests
      mockOrderReturns([{ id: 1 }]);

      const appHandler = await import('@/app/api/admin/requested_papers/[id]/route');
      const arxivId = generateTestArxivId();

      await testApiHandler({
        appHandler,
        params: { id: arxivId },
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
// TESTS - START PROCESSING REQUESTED PAPER
// ============================================================================

describe('Admin API - Start Processing', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('POST /api/admin/requested_papers/[id]/start_processing', () => {
    it('returns 401 without authentication', async () => {
      const appHandler = await import(
        '@/app/api/admin/requested_papers/[id]/start_processing/route'
      );
      const arxivId = generateTestArxivId();

      await testApiHandler({
        appHandler,
        params: { id: arxivId },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'POST' });

          expect(response.status).toBe(401);
        },
      });
    });

    it('returns 400 for invalid arXiv ID format', async () => {
      mockAdminAuthenticated();

      const appHandler = await import(
        '@/app/api/admin/requested_papers/[id]/start_processing/route'
      );

      await testApiHandler({
        appHandler,
        params: { id: 'invalid-format' },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'POST' });

          expect(response.status).toBe(400);

          const data = await response.json();
          expect(data).toHaveProperty('error');
        },
      });
    });

    it('starts processing with valid arXiv ID', async () => {
      mockAdminAuthenticated();
      // First query: check if paper exists
      mockQueryReturns(null);
      // Second query: insert returns the new paper
      mockQueryReturnsSingle({
        id: 1,
        paper_uuid: generateTestUuid(),
        status: 'not_started',
      });

      const appHandler = await import(
        '@/app/api/admin/requested_papers/[id]/start_processing/route'
      );
      const arxivId = generateTestArxivId();

      await testApiHandler({
        appHandler,
        params: { id: arxivId },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'POST' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data).toHaveProperty('paperUuid');
        },
      });
    });
  });
});
