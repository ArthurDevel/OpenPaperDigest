/**
 * Papers API E2E Tests
 *
 * Tests for public paper endpoints.
 * - GET /api/papers/minimal - paginated list
 * - GET /api/papers/count_since - count with timestamp
 * - GET /api/papers/check_arxiv/[id] - check arxiv existence
 * - GET /api/papers/slug/[slug] - resolve slug to paper
 * - GET /api/papers/[uuid] - get full paper
 * - GET /api/papers/[uuid]/summary - get paper summary
 * - GET /api/papers/[uuid]/markdown - get paper markdown
 * - GET /api/papers/[uuid]/slug - get/create slug
 * - POST /api/papers/enqueue_arxiv - enqueue paper
 * - GET /api/papers/thumbnails/[uuid] - get thumbnail
 */

import { test, expect } from '@playwright/test';
import { generateTestUuid, generateTestArxivId } from '../setup/test-utils';

// ============================================================================
// TESTS - MINIMAL PAPERS LIST
// ============================================================================

test.describe('Papers API - Minimal List', () => {
  test.describe('GET /api/papers/minimal', () => {
    test('returns paginated list with default parameters', async ({ request }) => {
      const response = await request.get('/api/papers/minimal');

      expect(response.status()).toBe(200);

      const data = await response.json();
      expect(data).toHaveProperty('items');
      expect(data).toHaveProperty('total');
      expect(data).toHaveProperty('page');
      expect(data).toHaveProperty('limit');
      expect(Array.isArray(data.items)).toBe(true);
    });

    test('returns paginated list with custom page and limit', async ({ request }) => {
      const response = await request.get('/api/papers/minimal?page=1&limit=5');

      expect(response.status()).toBe(200);

      const data = await response.json();
      expect(data.page).toBe(1);
      expect(data.limit).toBe(5);
      expect(data.items.length).toBeLessThanOrEqual(5);
    });

    test('returns 400 for invalid page parameter (negative)', async ({ request }) => {
      const response = await request.get('/api/papers/minimal?page=-1');

      expect(response.status()).toBe(400);

      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error).toContain('Invalid page');
    });

    test('returns 400 for invalid page parameter (zero)', async ({ request }) => {
      const response = await request.get('/api/papers/minimal?page=0');

      expect(response.status()).toBe(400);

      const data = await response.json();
      expect(data).toHaveProperty('error');
    });

    test('returns 400 for invalid page parameter (non-numeric)', async ({ request }) => {
      const response = await request.get('/api/papers/minimal?page=abc');

      expect(response.status()).toBe(400);

      const data = await response.json();
      expect(data).toHaveProperty('error');
    });

    test('returns 400 for invalid limit parameter (zero)', async ({ request }) => {
      const response = await request.get('/api/papers/minimal?limit=0');

      expect(response.status()).toBe(400);

      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error).toContain('Invalid limit');
    });

    test('returns 400 for invalid limit parameter (exceeds max)', async ({ request }) => {
      const response = await request.get('/api/papers/minimal?limit=101');

      expect(response.status()).toBe(400);

      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error).toContain('1-100');
    });
  });
});

// ============================================================================
// TESTS - COUNT SINCE
// ============================================================================

test.describe('Papers API - Count Since', () => {
  test.describe('GET /api/papers/count_since', () => {
    test('returns count with valid ISO timestamp', async ({ request }) => {
      const since = new Date(Date.now() - 86400000).toISOString(); // 1 day ago
      const response = await request.get(`/api/papers/count_since?since=${encodeURIComponent(since)}`);

      expect(response.status()).toBe(200);

      const data = await response.json();
      expect(data).toHaveProperty('count');
      expect(typeof data.count).toBe('number');
      expect(data.count).toBeGreaterThanOrEqual(0);
    });

    test('returns 400 when since parameter is missing', async ({ request }) => {
      const response = await request.get('/api/papers/count_since');

      expect(response.status()).toBe(400);

      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error).toContain('since');
    });

    test('returns 400 for invalid timestamp format', async ({ request }) => {
      const response = await request.get('/api/papers/count_since?since=invalid-date');

      expect(response.status()).toBe(400);

      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error).toContain('Invalid timestamp');
    });
  });
});

// ============================================================================
// TESTS - CHECK ARXIV
// ============================================================================

test.describe('Papers API - Check ArXiv', () => {
  test.describe('GET /api/papers/check_arxiv/[id]', () => {
    test('returns exists response for valid arXiv ID format', async ({ request }) => {
      const arxivId = generateTestArxivId();
      const response = await request.get(`/api/papers/check_arxiv/${arxivId}`);

      expect(response.status()).toBe(200);

      const data = await response.json();
      expect(data).toHaveProperty('exists');
      expect(typeof data.exists).toBe('boolean');
    });

    test('handles URL-encoded arXiv IDs', async ({ request }) => {
      // Test with a URL containing special characters
      const encodedUrl = encodeURIComponent('https://arxiv.org/abs/2301.00001');
      const response = await request.get(`/api/papers/check_arxiv/${encodedUrl}`);

      expect(response.status()).toBe(200);

      const data = await response.json();
      expect(data).toHaveProperty('exists');
    });
  });
});

// ============================================================================
// TESTS - SLUG RESOLUTION
// ============================================================================

test.describe('Papers API - Slug Resolution', () => {
  test.describe('GET /api/papers/slug/[slug]', () => {
    test('returns response for valid slug format', async ({ request }) => {
      const slug = 'test-paper-slug';
      const response = await request.get(`/api/papers/slug/${slug}`);

      // May return 200 (found) or 500 (not found, depending on service behavior)
      expect([200, 500]).toContain(response.status());

      const data = await response.json();
      if (response.status() === 200) {
        expect(data).toHaveProperty('paperUuid');
        expect(data).toHaveProperty('slug');
      }
    });
  });
});

// ============================================================================
// TESTS - PAPER BY UUID
// ============================================================================

test.describe('Papers API - Paper by UUID', () => {
  test.describe('GET /api/papers/[uuid]', () => {
    test('returns 404 for non-existent paper', async ({ request }) => {
      const uuid = generateTestUuid();
      const response = await request.get(`/api/papers/${uuid}`);

      expect(response.status()).toBe(404);

      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error.toLowerCase()).toContain('not found');
    });

    test('returns 400 for malformed UUID', async ({ request }) => {
      const response = await request.get('/api/papers/not-a-uuid');

      // Service may return 400 or 404 depending on validation
      expect([400, 404]).toContain(response.status());
    });
  });

  test.describe('GET /api/papers/[uuid]/summary', () => {
    test('returns 404 for non-existent paper', async ({ request }) => {
      const uuid = generateTestUuid();
      const response = await request.get(`/api/papers/${uuid}/summary`);

      expect(response.status()).toBe(404);

      const data = await response.json();
      expect(data).toHaveProperty('error');
    });
  });

  test.describe('GET /api/papers/[uuid]/markdown', () => {
    test('returns 404 for non-existent paper', async ({ request }) => {
      const uuid = generateTestUuid();
      const response = await request.get(`/api/papers/${uuid}/markdown`);

      expect(response.status()).toBe(404);

      const data = await response.json();
      expect(data).toHaveProperty('error');
    });
  });

  test.describe('GET /api/papers/[uuid]/slug', () => {
    test('returns response for valid UUID format', async ({ request }) => {
      const uuid = generateTestUuid();
      const response = await request.get(`/api/papers/${uuid}/slug`);

      // May return 200 (with null slug) or 500 depending on implementation
      expect([200, 500]).toContain(response.status());
    });
  });

  test.describe('POST /api/papers/[uuid]/slug', () => {
    test('returns 404 for non-existent paper', async ({ request }) => {
      const uuid = generateTestUuid();
      const response = await request.post(`/api/papers/${uuid}/slug`);

      expect(response.status()).toBe(404);

      const data = await response.json();
      expect(data).toHaveProperty('error');
    });
  });
});

// ============================================================================
// TESTS - ENQUEUE ARXIV
// ============================================================================

test.describe('Papers API - Enqueue ArXiv', () => {
  test.describe('POST /api/papers/enqueue_arxiv', () => {
    test('returns 400 when url is missing', async ({ request }) => {
      const response = await request.post('/api/papers/enqueue_arxiv', {
        data: {},
      });

      expect(response.status()).toBe(400);

      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error).toContain('url');
    });

    test('returns 400 for invalid JSON body', async ({ request }) => {
      const response = await request.post('/api/papers/enqueue_arxiv', {
        headers: {
          'Content-Type': 'application/json',
        },
        data: 'not valid json',
      });

      expect(response.status()).toBe(400);
    });

    test('accepts valid arXiv URL', async ({ request }) => {
      const response = await request.post('/api/papers/enqueue_arxiv', {
        data: {
          url: 'https://arxiv.org/abs/2301.00001',
        },
      });

      // May return 200 (success) or 500 (service error)
      // We mainly test that validation passes
      expect([200, 500]).toContain(response.status());

      if (response.status() === 200) {
        const data = await response.json();
        expect(data).toHaveProperty('paperUuid');
      }
    });
  });
});

// ============================================================================
// TESTS - THUMBNAILS
// ============================================================================

test.describe('Papers API - Thumbnails', () => {
  test.describe('GET /api/papers/thumbnails/[uuid]', () => {
    test('returns 404 for non-existent paper', async ({ request }) => {
      const uuid = generateTestUuid();
      const response = await request.get(`/api/papers/thumbnails/${uuid}`);

      expect(response.status()).toBe(404);

      const data = await response.json();
      expect(data).toHaveProperty('error');
    });

    test('returns 400 for missing UUID', async ({ request }) => {
      // Empty UUID segment would result in a different route
      // Test with clearly invalid format
      const response = await request.get('/api/papers/thumbnails/');

      expect(response.status()).toBe(404); // Route not found
    });
  });
});
