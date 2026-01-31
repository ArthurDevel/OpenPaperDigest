/**
 * ArXiv Metadata API Integration Tests
 *
 * Tests for the arXiv metadata endpoint using mocked arXiv API.
 * - GET /api/arxiv-metadata/[id] - fetch arxiv metadata
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { testApiHandler } from 'next-test-api-route-handler';
import { resetAllMocks, generateTestArxivId } from './setup';

// Mock the arxiv lib fetchMetadata function
vi.mock('@/lib/arxiv', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/arxiv')>();
  return {
    ...original,
    fetchMetadata: vi.fn(),
  };
});

import { fetchMetadata } from '@/lib/arxiv';
const mockFetchMetadata = fetchMetadata as ReturnType<typeof vi.fn>;

// ============================================================================
// TESTS - ARXIV METADATA
// ============================================================================

describe('ArXiv Metadata API', () => {
  beforeEach(() => {
    resetAllMocks();
    vi.clearAllMocks();
  });

  describe('GET /api/arxiv-metadata/[id]', () => {
    it('returns metadata for valid arXiv ID', async () => {
      const mockMetadata = {
        arxivId: '2301.00001',
        title: 'Test Paper Title',
        authors: ['Author One', 'Author Two'],
        abstract: 'This is the abstract.',
        publishedAt: new Date('2023-01-01'),
        categories: ['cs.LG', 'cs.AI'],
      };
      mockFetchMetadata.mockResolvedValue(mockMetadata);

      const appHandler = await import('@/app/api/arxiv-metadata/[id]/route');

      await testApiHandler({
        appHandler,
        params: { id: '2301.00001' },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data).toHaveProperty('arxivId');
          expect(data).toHaveProperty('title');
          expect(data).toHaveProperty('authors');
          expect(data).toHaveProperty('abstract');
          expect(data.arxivId).toBe('2301.00001');
        },
      });
    });

    it('handles URL-encoded arXiv URLs', async () => {
      const mockMetadata = {
        arxivId: '2301.00001',
        title: 'Test Paper',
        authors: ['Author'],
        abstract: 'Abstract',
        publishedAt: new Date(),
        categories: [],
      };
      mockFetchMetadata.mockResolvedValue(mockMetadata);

      const appHandler = await import('@/app/api/arxiv-metadata/[id]/route');
      const encodedUrl = encodeURIComponent('https://arxiv.org/abs/2301.00001');

      await testApiHandler({
        appHandler,
        params: { id: encodedUrl },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data).toHaveProperty('arxivId');
        },
      });
    });

    it('returns 400 for invalid arXiv ID format', async () => {
      const appHandler = await import('@/app/api/arxiv-metadata/[id]/route');

      await testApiHandler({
        appHandler,
        params: { id: 'not-valid-id' },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(400);

          const data = await response.json();
          expect(data).toHaveProperty('error');
        },
      });
    });

    it('returns 404 for non-existent arXiv paper', async () => {
      mockFetchMetadata.mockRejectedValue(new Error('No metadata found for arXiv ID: 9999.99999'));

      const appHandler = await import('@/app/api/arxiv-metadata/[id]/route');

      await testApiHandler({
        appHandler,
        params: { id: '9999.99999' },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(404);

          const data = await response.json();
          expect(data).toHaveProperty('error');
          expect(data.error.toLowerCase()).toContain('no metadata found');
        },
      });
    });

    it('handles old-style arXiv IDs with slashes', async () => {
      const mockMetadata = {
        arxivId: 'cond-mat/0001001',
        title: 'Old Style Paper',
        authors: ['Author'],
        abstract: 'Abstract',
        publishedAt: new Date(),
        categories: ['cond-mat'],
      };
      mockFetchMetadata.mockResolvedValue(mockMetadata);

      const appHandler = await import('@/app/api/arxiv-metadata/[id]/route');
      const oldStyleId = encodeURIComponent('cond-mat/0001001');

      await testApiHandler({
        appHandler,
        params: { id: oldStyleId },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data).toHaveProperty('arxivId');
        },
      });
    });

    it('returns JSON content type', async () => {
      const mockMetadata = {
        arxivId: '2301.00001',
        title: 'Test',
        authors: [],
        abstract: '',
        publishedAt: new Date(),
        categories: [],
      };
      mockFetchMetadata.mockResolvedValue(mockMetadata);

      const appHandler = await import('@/app/api/arxiv-metadata/[id]/route');

      await testApiHandler({
        appHandler,
        params: { id: '2301.00001' },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          const contentType = response.headers.get('content-type');
          expect(contentType).toContain('application/json');
        },
      });
    });

    it('returns 500 for arXiv API errors', async () => {
      mockFetchMetadata.mockRejectedValue(new Error('arXiv API request failed'));

      const appHandler = await import('@/app/api/arxiv-metadata/[id]/route');

      await testApiHandler({
        appHandler,
        params: { id: '2301.00001' },
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(500);

          const data = await response.json();
          expect(data).toHaveProperty('error');
        },
      });
    });
  });
});
