/**
 * Papers API Integration Tests
 *
 * Tests for public paper endpoints using mocked database layer.
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

import { describe, it, expect, beforeEach } from 'vitest';
import { testApiHandler } from 'next-test-api-route-handler';
import {
  resetAllMocks,
  generateTestUuid,
  generateTestArxivId,
  mockQueryReturns,
  mockQueryReturnsSingle,
  mockCountReturns,
  mockGteCountReturns,
  mockRangeReturns,
  mockOrderReturns,
} from './setup';

// ============================================================================
// TESTS - MINIMAL PAPERS LIST
// ============================================================================

describe('Papers API - Minimal List', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('GET /api/papers/minimal', () => {
    it('returns paginated list with default parameters', async () => {
      // Mock count query
      mockCountReturns(2);

      // Mock papers query (via range)
      mockRangeReturns([
        {
          paper_uuid: generateTestUuid(),
          title: 'Test Paper 1',
          authors: 'Author 1',
          thumbnail_data_url: null,
        },
        {
          paper_uuid: generateTestUuid(),
          title: 'Test Paper 2',
          authors: 'Author 2',
          thumbnail_data_url: null,
        },
      ]);

      // Mock slugs query
      mockOrderReturns([]);

      const appHandler = await import('@/app/api/papers/minimal/route');

      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data).toHaveProperty('items');
          expect(data).toHaveProperty('page');
          expect(data).toHaveProperty('limit');
          expect(data).toHaveProperty('hasMore');
          expect(Array.isArray(data.items)).toBe(true);
          expect(data.items.length).toBe(2);
        },
      });
    });

    it('returns paginated list with custom page and limit', async () => {
      mockCountReturns(0);
      mockRangeReturns([]);
      mockOrderReturns([]);

      const appHandler = await import('@/app/api/papers/minimal/route');

      await testApiHandler({
        appHandler,
        url: '/api/papers/minimal?page=2&limit=5',
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data.page).toBe(2);
          expect(data.limit).toBe(5);
        },
      });
    });

    it('returns 400 for invalid page parameter (negative)', async () => {
      const appHandler = await import('@/app/api/papers/minimal/route');

      await testApiHandler({
        appHandler,
        url: '/api/papers/minimal?page=-1',
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(400);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error).toContain('Invalid page');
        },
      });
    });

    it('returns 400 for invalid page parameter (zero)', async () => {
      const appHandler = await import('@/app/api/papers/minimal/route');

      await testApiHandler({
        appHandler,
        url: '/api/papers/minimal?page=0',
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(400);

          const data = await response.json();
          expect(data).toHaveProperty('error');
        },
      });
    });

    it('returns 400 for invalid page parameter (non-numeric)', async () => {
      const appHandler = await import('@/app/api/papers/minimal/route');

      await testApiHandler({
        appHandler,
        url: '/api/papers/minimal?page=abc',
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(400);

          const data = await response.json();
          expect(data).toHaveProperty('error');
        },
      });
    });

    it('returns 400 for invalid limit parameter (zero)', async () => {
      const appHandler = await import('@/app/api/papers/minimal/route');

      await testApiHandler({
        appHandler,
        url: '/api/papers/minimal?limit=0',
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(400);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error).toContain('Invalid limit');
        },
      });
    });

    it('returns 400 for invalid limit parameter (exceeds max)', async () => {
      const appHandler = await import('@/app/api/papers/minimal/route');

      await testApiHandler({
        appHandler,
        url: '/api/papers/minimal?limit=101',
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(400);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error).toContain('1-100');
        },
      });
    });
  });
});

// ============================================================================
// TESTS - COUNT SINCE
// ============================================================================

describe('Papers API - Count Since', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('GET /api/papers/count_since', () => {
    it('returns count with valid ISO timestamp', async () => {
      // Query ends with .gte() for timestamp comparison with count option
      mockGteCountReturns(5);

      const appHandler = await import('@/app/api/papers/count_since/route');
      const since = new Date(Date.now() - 86400000).toISOString();

      await testApiHandler({
        appHandler,
        url: `/api/papers/count_since?since=${encodeURIComponent(since)}`,
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data).toHaveProperty('count');
          expect(typeof data.count).toBe('number');
          expect(data.count).toBe(5);
        },
      });
    });

    it('returns 400 when since parameter is missing', async () => {
      const appHandler = await import('@/app/api/papers/count_since/route');

      await testApiHandler({
        appHandler,
        url: '/api/papers/count_since',
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(400);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error.toLowerCase()).toContain('since');
        },
      });
    });

    it('returns 400 for invalid timestamp format', async () => {
      const appHandler = await import('@/app/api/papers/count_since/route');

      await testApiHandler({
        appHandler,
        url: '/api/papers/count_since?since=invalid-date',
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(400);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error).toContain('Invalid timestamp');
        },
      });
    });
  });
});

// ============================================================================
// TESTS - CHECK ARXIV
// ============================================================================

describe('Papers API - Check ArXiv', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('GET /api/papers/check_arxiv/[id]', () => {
    it('returns exists: false for non-existent paper', async () => {
      mockQueryReturns(null);

      const appHandler = await import('@/app/api/papers/check_arxiv/[id]/route');
      const arxivId = generateTestArxivId();

      await testApiHandler({
        appHandler,
        params: { id: arxivId },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data).toHaveProperty('exists');
          expect(data.exists).toBe(false);
        },
      });
    });

    it('returns exists: true for completed paper', async () => {
      const paperUuid = generateTestUuid();
      // First query: paper lookup
      mockQueryReturns({
        paper_uuid: paperUuid,
        status: 'completed',
      });
      // Second query: slug lookup
      mockQueryReturns({ slug: 'test-paper-slug' });

      const appHandler = await import('@/app/api/papers/check_arxiv/[id]/route');
      const arxivId = generateTestArxivId();

      await testApiHandler({
        appHandler,
        params: { id: arxivId },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data.exists).toBe(true);
          expect(data.viewerUrl).toBeDefined();
        },
      });
    });
  });
});

// ============================================================================
// TESTS - SLUG RESOLUTION
// ============================================================================

describe('Papers API - Slug Resolution', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('GET /api/papers/slug/[slug]', () => {
    it('returns paper data for valid slug', async () => {
      const paperUuid = generateTestUuid();
      mockQueryReturns({
        slug: 'test-paper-slug',
        paper_uuid: paperUuid,
        tombstone: false,
      });

      const appHandler = await import('@/app/api/papers/slug/[slug]/route');

      await testApiHandler({
        appHandler,
        params: { slug: 'test-paper-slug' },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data).toHaveProperty('paperUuid');
          expect(data).toHaveProperty('slug');
          expect(data.paperUuid).toBe(paperUuid);
        },
      });
    });

    it('returns null paperUuid for non-existent slug', async () => {
      mockQueryReturns(null);

      const appHandler = await import('@/app/api/papers/slug/[slug]/route');

      await testApiHandler({
        appHandler,
        params: { slug: 'non-existent-slug' },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data.paperUuid).toBeNull();
        },
      });
    });
  });
});

// ============================================================================
// TESTS - PAPER BY UUID
// ============================================================================

describe('Papers API - Paper by UUID', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('GET /api/papers/[uuid]', () => {
    it('returns 404 for non-existent paper', async () => {
      mockQueryReturns(null);

      const appHandler = await import('@/app/api/papers/[uuid]/route');
      const uuid = generateTestUuid();

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(404);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error.toLowerCase()).toContain('not found');
        },
      });
    });

    it('returns paper data for existing paper', async () => {
      const uuid = generateTestUuid();
      mockQueryReturns({
        paper_uuid: uuid,
        title: 'Test Paper',
        authors: 'Test Author',
        arxiv_url: 'https://arxiv.org/abs/2301.00001',
        thumbnail_data_url: null,
        processed_content: JSON.stringify({ some: 'content' }),
        processing_time_seconds: 120,
      });

      const appHandler = await import('@/app/api/papers/[uuid]/route');

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          // getPaperJson returns paperId (not paperUuid)
          expect(data.paperId).toBe(uuid);
        },
      });
    });
  });

  describe('GET /api/papers/[uuid]/summary', () => {
    it('returns 404 for non-existent paper', async () => {
      mockQueryReturns(null);

      const appHandler = await import('@/app/api/papers/[uuid]/summary/route');
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

    it('returns summary for existing paper', async () => {
      const uuid = generateTestUuid();
      mockQueryReturns({
        paper_uuid: uuid,
        title: 'Test Paper',
        authors: 'Test Author',
        arxiv_url: 'https://arxiv.org/abs/2301.00001',
        processed_content: JSON.stringify({ five_minute_summary: 'Summary text' }),
        num_pages: 10,
      });

      const appHandler = await import('@/app/api/papers/[uuid]/summary/route');

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data).toHaveProperty('paperId');
          expect(data).toHaveProperty('title');
          expect(data).toHaveProperty('authors');
        },
      });
    });
  });

  describe('GET /api/papers/[uuid]/markdown', () => {
    it('returns 404 for non-existent paper', async () => {
      mockQueryReturns(null);

      const appHandler = await import('@/app/api/papers/[uuid]/markdown/route');
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

    it('returns markdown for existing paper', async () => {
      mockQueryReturns({
        processed_content: JSON.stringify({ final_markdown: '# Test Markdown' }),
      });

      const appHandler = await import('@/app/api/papers/[uuid]/markdown/route');
      const uuid = generateTestUuid();

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          // Markdown is returned as plain text, not JSON
          const text = await response.text();
          expect(text).toBe('# Test Markdown');
        },
      });
    });
  });
});

// ============================================================================
// TESTS - ENQUEUE ARXIV
// ============================================================================

describe('Papers API - Enqueue ArXiv', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('POST /api/papers/enqueue_arxiv', () => {
    it('returns 400 when url is missing', async () => {
      const appHandler = await import('@/app/api/papers/enqueue_arxiv/route');

      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({
            method: 'POST',
            body: JSON.stringify({}),
            headers: { 'Content-Type': 'application/json' },
          });

          expect(response.status).toBe(400);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error.toLowerCase()).toContain('url');
        },
      });
    });

    it('creates new paper for valid arXiv URL', async () => {
      const paperUuid = generateTestUuid();
      // First query: check if paper exists
      mockQueryReturns(null);
      // Second query: insert returns the new paper
      mockQueryReturnsSingle({
        id: 1,
        paper_uuid: paperUuid,
        status: 'not_started',
      });

      const appHandler = await import('@/app/api/papers/enqueue_arxiv/route');

      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({
            method: 'POST',
            body: JSON.stringify({ url: 'https://arxiv.org/abs/2301.00001' }),
            headers: { 'Content-Type': 'application/json' },
          });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data).toHaveProperty('paperUuid');
          expect(data).toHaveProperty('status');
        },
      });
    });

    it('returns existing paper if already enqueued', async () => {
      const paperUuid = generateTestUuid();
      mockQueryReturns({
        id: 1,
        paper_uuid: paperUuid,
        status: 'processing',
      });

      const appHandler = await import('@/app/api/papers/enqueue_arxiv/route');

      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({
            method: 'POST',
            body: JSON.stringify({ url: 'https://arxiv.org/abs/2301.00001' }),
            headers: { 'Content-Type': 'application/json' },
          });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data.paperUuid).toBe(paperUuid);
          expect(data.status).toBe('processing');
        },
      });
    });
  });
});

// ============================================================================
// TESTS - THUMBNAILS
// ============================================================================

describe('Papers API - Thumbnails', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('GET /api/papers/thumbnails/[uuid]', () => {
    it('returns 404 for non-existent paper', async () => {
      mockQueryReturns(null);

      const appHandler = await import('@/app/api/papers/thumbnails/[uuid]/route');
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

    it('returns 404 for paper without thumbnail', async () => {
      mockQueryReturns({
        thumbnail_data_url: null,
      });

      const appHandler = await import('@/app/api/papers/thumbnails/[uuid]/route');
      const uuid = generateTestUuid();

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(404);
        },
      });
    });

    it('returns thumbnail image for paper with valid thumbnail', async () => {
      // Base64 encoded 1x1 transparent PNG
      const base64Png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';
      mockQueryReturns({
        thumbnail_data_url: `data:image/png;base64,${base64Png}`,
      });

      const appHandler = await import('@/app/api/papers/thumbnails/[uuid]/route');
      const uuid = generateTestUuid();

      await testApiHandler({
        appHandler,
        params: { uuid },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);
          expect(response.headers.get('content-type')).toBe('image/png');
        },
      });
    });
  });
});
