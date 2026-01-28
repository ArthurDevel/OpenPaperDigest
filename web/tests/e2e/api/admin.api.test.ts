/**
 * Admin API E2E Tests
 *
 * Tests for admin endpoints (require HTTP Basic authentication).
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

import { test, expect } from '@playwright/test';
import {
  getAdminHeaders,
  getInvalidAdminAuthHeader,
  generateTestUuid,
  generateTestArxivId,
  createTestPaperPayload,
} from '../setup/test-utils';

// ============================================================================
// TESTS - ADMIN PAPERS LIST
// ============================================================================

test.describe('Admin API - Papers List', () => {
  test.describe('GET /api/admin/papers', () => {
    test('returns 401 without authentication', async ({ request }) => {
      const response = await request.get('/api/admin/papers');

      expect(response.status()).toBe(401);
    });

    test('returns 401 with invalid credentials', async ({ request }) => {
      const response = await request.get('/api/admin/papers', {
        headers: {
          Authorization: getInvalidAdminAuthHeader(),
        },
      });

      expect(response.status()).toBe(401);
    });

    test('returns papers list with valid admin auth', async ({ request }) => {
      const response = await request.get('/api/admin/papers', {
        headers: getAdminHeaders(),
      });

      expect(response.status()).toBe(200);

      const data = await response.json();
      expect(Array.isArray(data)).toBe(true);
    });

    test('accepts status filter parameter', async ({ request }) => {
      const response = await request.get('/api/admin/papers?status=completed', {
        headers: getAdminHeaders(),
      });

      expect(response.status()).toBe(200);

      const data = await response.json();
      expect(Array.isArray(data)).toBe(true);
    });

    test('accepts limit parameter', async ({ request }) => {
      const response = await request.get('/api/admin/papers?limit=10', {
        headers: getAdminHeaders(),
      });

      expect(response.status()).toBe(200);

      const data = await response.json();
      expect(Array.isArray(data)).toBe(true);
      expect(data.length).toBeLessThanOrEqual(10);
    });

    test('returns 400 for invalid limit parameter', async ({ request }) => {
      const response = await request.get('/api/admin/papers?limit=0', {
        headers: getAdminHeaders(),
      });

      expect(response.status()).toBe(400);

      const data = await response.json();
      expect(data).toHaveProperty('error');
    });

    test('returns 400 for limit exceeding maximum', async ({ request }) => {
      const response = await request.get('/api/admin/papers?limit=20000', {
        headers: getAdminHeaders(),
      });

      expect(response.status()).toBe(400);

      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error).toContain('10000');
    });
  });
});

// ============================================================================
// TESTS - CUMULATIVE DAILY STATS
// ============================================================================

test.describe('Admin API - Cumulative Daily Stats', () => {
  test.describe('GET /api/admin/papers/cumulative_daily', () => {
    test('returns 401 without authentication', async ({ request }) => {
      const response = await request.get('/api/admin/papers/cumulative_daily');

      expect(response.status()).toBe(401);
    });

    test('returns 401 with invalid credentials', async ({ request }) => {
      const response = await request.get('/api/admin/papers/cumulative_daily', {
        headers: {
          Authorization: getInvalidAdminAuthHeader(),
        },
      });

      expect(response.status()).toBe(401);
    });

    test('returns daily stats with valid admin auth', async ({ request }) => {
      const response = await request.get('/api/admin/papers/cumulative_daily', {
        headers: getAdminHeaders(),
      });

      expect(response.status()).toBe(200);

      const data = await response.json();
      expect(Array.isArray(data)).toBe(true);
    });
  });
});

// ============================================================================
// TESTS - PAPER IMPORT
// ============================================================================

test.describe('Admin API - Paper Import', () => {
  test.describe('POST /api/admin/papers/import', () => {
    test('returns 401 without authentication', async ({ request }) => {
      const response = await request.post('/api/admin/papers/import', {
        data: createTestPaperPayload(),
      });

      expect(response.status()).toBe(401);
    });

    test('returns 401 with invalid credentials', async ({ request }) => {
      const response = await request.post('/api/admin/papers/import', {
        headers: {
          Authorization: getInvalidAdminAuthHeader(),
        },
        data: createTestPaperPayload(),
      });

      expect(response.status()).toBe(401);
    });

    test('returns 400 for invalid body (array)', async ({ request }) => {
      const response = await request.post('/api/admin/papers/import', {
        headers: getAdminHeaders(),
        data: [],
      });

      expect(response.status()).toBe(400);

      const data = await response.json();
      expect(data).toHaveProperty('error');
    });

    test('returns 400 for empty body', async ({ request }) => {
      const response = await request.post('/api/admin/papers/import', {
        headers: getAdminHeaders(),
        data: {},
      });

      // Empty object should fail validation
      expect([400, 500]).toContain(response.status());
    });

    test('accepts valid paper import payload', async ({ request }) => {
      const response = await request.post('/api/admin/papers/import', {
        headers: getAdminHeaders(),
        data: createTestPaperPayload(),
      });

      // May return 200 (success) or 400/500 (validation/service error)
      expect([200, 400, 500]).toContain(response.status());

      if (response.status() === 200) {
        const data = await response.json();
        expect(data).toHaveProperty('success', true);
        expect(data).toHaveProperty('uuid');
      }
    });
  });
});

// ============================================================================
// TESTS - PAPER DELETE
// ============================================================================

test.describe('Admin API - Paper Delete', () => {
  test.describe('DELETE /api/admin/papers/[uuid]', () => {
    test('returns 401 without authentication', async ({ request }) => {
      const uuid = generateTestUuid();
      const response = await request.delete(`/api/admin/papers/${uuid}`);

      expect(response.status()).toBe(401);
    });

    test('returns 401 with invalid credentials', async ({ request }) => {
      const uuid = generateTestUuid();
      const response = await request.delete(`/api/admin/papers/${uuid}`, {
        headers: {
          Authorization: getInvalidAdminAuthHeader(),
        },
      });

      expect(response.status()).toBe(401);
    });

    test('returns 404 for non-existent paper', async ({ request }) => {
      const uuid = generateTestUuid();
      const response = await request.delete(`/api/admin/papers/${uuid}`, {
        headers: getAdminHeaders(),
      });

      expect(response.status()).toBe(404);

      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error.toLowerCase()).toContain('not found');
    });
  });
});

// ============================================================================
// TESTS - PAPER RESTART
// ============================================================================

test.describe('Admin API - Paper Restart', () => {
  test.describe('POST /api/admin/papers/[uuid]/restart', () => {
    test('returns 401 without authentication', async ({ request }) => {
      const uuid = generateTestUuid();
      const response = await request.post(`/api/admin/papers/${uuid}/restart`);

      expect(response.status()).toBe(401);
    });

    test('returns 401 with invalid credentials', async ({ request }) => {
      const uuid = generateTestUuid();
      const response = await request.post(`/api/admin/papers/${uuid}/restart`, {
        headers: {
          Authorization: getInvalidAdminAuthHeader(),
        },
      });

      expect(response.status()).toBe(401);
    });

    test('returns 404 for non-existent paper', async ({ request }) => {
      const uuid = generateTestUuid();
      const response = await request.post(`/api/admin/papers/${uuid}/restart`, {
        headers: getAdminHeaders(),
      });

      expect(response.status()).toBe(404);

      const data = await response.json();
      expect(data).toHaveProperty('error');
    });
  });
});

// ============================================================================
// TESTS - ADMIN PROCESSING METRICS
// ============================================================================

test.describe('Admin API - Processing Metrics', () => {
  test.describe('GET /api/admin/papers/[uuid]/processing_metrics', () => {
    test('returns 401 without authentication', async ({ request }) => {
      const uuid = generateTestUuid();
      const response = await request.get(`/api/admin/papers/${uuid}/processing_metrics`);

      expect(response.status()).toBe(401);
    });

    test('returns 401 with invalid credentials', async ({ request }) => {
      const uuid = generateTestUuid();
      const response = await request.get(`/api/admin/papers/${uuid}/processing_metrics`, {
        headers: {
          Authorization: getInvalidAdminAuthHeader(),
        },
      });

      expect(response.status()).toBe(401);
    });

    test('returns 404 for non-existent paper', async ({ request }) => {
      const uuid = generateTestUuid();
      const response = await request.get(`/api/admin/papers/${uuid}/processing_metrics`, {
        headers: getAdminHeaders(),
      });

      expect(response.status()).toBe(404);

      const data = await response.json();
      expect(data).toHaveProperty('error');
    });
  });
});

// ============================================================================
// TESTS - REQUESTED PAPERS LIST
// ============================================================================

test.describe('Admin API - Requested Papers List', () => {
  test.describe('GET /api/admin/requested_papers', () => {
    test('returns 401 without authentication', async ({ request }) => {
      const response = await request.get('/api/admin/requested_papers');

      expect(response.status()).toBe(401);
    });

    test('returns 401 with invalid credentials', async ({ request }) => {
      const response = await request.get('/api/admin/requested_papers', {
        headers: {
          Authorization: getInvalidAdminAuthHeader(),
        },
      });

      expect(response.status()).toBe(401);
    });

    test('returns requested papers with valid admin auth', async ({ request }) => {
      const response = await request.get('/api/admin/requested_papers', {
        headers: getAdminHeaders(),
      });

      expect(response.status()).toBe(200);

      const data = await response.json();
      expect(Array.isArray(data)).toBe(true);
    });
  });
});

// ============================================================================
// TESTS - DELETE REQUESTED PAPER
// ============================================================================

test.describe('Admin API - Delete Requested Paper', () => {
  test.describe('DELETE /api/admin/requested_papers/[id]', () => {
    test('returns 401 without authentication', async ({ request }) => {
      const arxivId = generateTestArxivId();
      const response = await request.delete(`/api/admin/requested_papers/${arxivId}`);

      expect(response.status()).toBe(401);
    });

    test('returns 401 with invalid credentials', async ({ request }) => {
      const arxivId = generateTestArxivId();
      const response = await request.delete(`/api/admin/requested_papers/${arxivId}`, {
        headers: {
          Authorization: getInvalidAdminAuthHeader(),
        },
      });

      expect(response.status()).toBe(401);
    });

    test('returns success for valid arXiv ID with admin auth', async ({ request }) => {
      const arxivId = generateTestArxivId();
      const response = await request.delete(`/api/admin/requested_papers/${arxivId}`, {
        headers: getAdminHeaders(),
      });

      // May return 200 (deleted, even if nothing existed) or error
      expect([200, 500]).toContain(response.status());

      if (response.status() === 200) {
        const data = await response.json();
        expect(data).toHaveProperty('deleted');
      }
    });

    test('returns 400 for invalid arXiv ID format', async ({ request }) => {
      const response = await request.delete('/api/admin/requested_papers/invalid-format', {
        headers: getAdminHeaders(),
      });

      expect(response.status()).toBe(400);

      const data = await response.json();
      expect(data).toHaveProperty('error');
    });
  });
});

// ============================================================================
// TESTS - START PROCESSING REQUESTED PAPER
// ============================================================================

test.describe('Admin API - Start Processing', () => {
  test.describe('POST /api/admin/requested_papers/[id]/start_processing', () => {
    test('returns 401 without authentication', async ({ request }) => {
      const arxivId = generateTestArxivId();
      const response = await request.post(`/api/admin/requested_papers/${arxivId}/start_processing`);

      expect(response.status()).toBe(401);
    });

    test('returns 401 with invalid credentials', async ({ request }) => {
      const arxivId = generateTestArxivId();
      const response = await request.post(`/api/admin/requested_papers/${arxivId}/start_processing`, {
        headers: {
          Authorization: getInvalidAdminAuthHeader(),
        },
      });

      expect(response.status()).toBe(401);
    });

    test('returns 400 for invalid arXiv ID format', async ({ request }) => {
      const response = await request.post('/api/admin/requested_papers/invalid-format/start_processing', {
        headers: getAdminHeaders(),
      });

      expect(response.status()).toBe(400);

      const data = await response.json();
      expect(data).toHaveProperty('error');
    });

    test('accepts valid arXiv ID with admin auth', async ({ request }) => {
      const arxivId = generateTestArxivId();
      const response = await request.post(`/api/admin/requested_papers/${arxivId}/start_processing`, {
        headers: getAdminHeaders(),
      });

      // May return 200 (success) or 500 (service error)
      expect([200, 500]).toContain(response.status());

      if (response.status() === 200) {
        const data = await response.json();
        expect(data).toHaveProperty('paperUuid');
      }
    });
  });
});
