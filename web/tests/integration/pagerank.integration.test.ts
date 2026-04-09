/**
 * PageRank API Integration Tests
 *
 * Tests for the GET /api/pagerank endpoint using mocked database layer.
 * - GET /api/pagerank - returns scatter chart data with best author percentile per paper
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { testApiHandler } from 'next-test-api-route-handler';
import {
  resetAllMocks,
  mockNotReturns,
} from './setup';

// ============================================================================
// TESTS - PAGERANK SCATTER DATA
// ============================================================================

describe('PageRank API', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  describe('GET /api/pagerank', () => {
    it('returns array of objects with created_at, title, arxiv_id, best_author_percentile fields', async () => {
      mockNotReturns([
        {
          papers: { id: 1, created_at: '2025-01-10T00:00:00Z', title: 'Paper A', arxiv_id: '2501.00001' },
          authors: { pagerank: { percentile: 85.5 } },
        },
        {
          papers: { id: 1, created_at: '2025-01-10T00:00:00Z', title: 'Paper A', arxiv_id: '2501.00001' },
          authors: { pagerank: { percentile: 92.3 } },
        },
        {
          papers: { id: 2, created_at: '2025-01-12T00:00:00Z', title: 'Paper B', arxiv_id: '2501.00002' },
          authors: { pagerank: { percentile: 45.0 } },
        },
      ]);

      const appHandler = await import('@/app/api/pagerank/route');

      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(Array.isArray(data)).toBe(true);
          expect(data).toHaveLength(2);

          // Paper A should have max percentile of 92.3 (two authors: 85.5 and 92.3)
          expect(data[0]).toEqual({
            createdAt: '2025-01-10T00:00:00Z',
            title: 'Paper A',
            arxivId: '2501.00001',
            bestAuthorPercentile: 92.3,
          });

          // Paper B has single author with 45.0
          expect(data[1]).toEqual({
            createdAt: '2025-01-12T00:00:00Z',
            title: 'Paper B',
            arxivId: '2501.00002',
            bestAuthorPercentile: 45.0,
          });
        },
      });
    });

    it('returns empty array when no papers have author pagerank data', async () => {
      mockNotReturns([]);

      const appHandler = await import('@/app/api/pagerank/route');

      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(Array.isArray(data)).toBe(true);
          expect(data).toHaveLength(0);
        },
      });
    });
  });
});
