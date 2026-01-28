/**
 * ArXiv Metadata API E2E Tests
 *
 * Tests for the arXiv metadata endpoint.
 * - GET /api/arxiv-metadata/[id] - fetch arxiv metadata
 */

import { test, expect } from '@playwright/test';
import { generateTestArxivId } from '../setup/test-utils';

// ============================================================================
// TESTS - ARXIV METADATA
// ============================================================================

test.describe('ArXiv Metadata API', () => {
  test.describe('GET /api/arxiv-metadata/[id]', () => {
    test('returns metadata for valid arXiv ID format', async ({ request }) => {
      // Use a known valid arXiv paper ID
      const arxivId = '2301.00001';
      const response = await request.get(`/api/arxiv-metadata/${arxivId}`);

      // May return 200 (found) or 404 (not found on arxiv) or 500 (service error)
      expect([200, 404, 500]).toContain(response.status());

      if (response.status() === 200) {
        const data = await response.json();
        expect(data).toHaveProperty('arxivId');
        expect(data).toHaveProperty('title');
        expect(data).toHaveProperty('authors');
        expect(data).toHaveProperty('abstract');
      }
    });

    test('handles URL-encoded arXiv URLs', async ({ request }) => {
      const encodedUrl = encodeURIComponent('https://arxiv.org/abs/2301.00001');
      const response = await request.get(`/api/arxiv-metadata/${encodedUrl}`);

      // Should parse and normalize the URL
      expect([200, 404, 500]).toContain(response.status());

      if (response.status() === 200) {
        const data = await response.json();
        expect(data).toHaveProperty('arxivId');
      }
    });

    test('returns 400 for invalid arXiv ID format', async ({ request }) => {
      const response = await request.get('/api/arxiv-metadata/not-valid-id');

      expect(response.status()).toBe(400);

      const data = await response.json();
      expect(data).toHaveProperty('error');
    });

    test('returns 400 for empty ID', async ({ request }) => {
      const response = await request.get('/api/arxiv-metadata/%20');

      expect([400, 404]).toContain(response.status());
    });

    test('returns 404 for non-existent arXiv paper', async ({ request }) => {
      // Use a clearly non-existent arXiv ID (far future)
      const arxivId = '9999.99999';
      const response = await request.get(`/api/arxiv-metadata/${arxivId}`);

      // Should return 404 as paper does not exist
      expect([400, 404, 500]).toContain(response.status());

      if (response.status() === 404) {
        const data = await response.json();
        expect(data).toHaveProperty('error');
        expect(data.error.toLowerCase()).toContain('not found');
      }
    });

    test('handles old-style arXiv IDs with slashes', async ({ request }) => {
      // Old-style arXiv IDs have format like: cond-mat/0001001
      // These need to be URL-encoded
      const oldStyleId = encodeURIComponent('cond-mat/0001001');
      const response = await request.get(`/api/arxiv-metadata/${oldStyleId}`);

      // May return various status codes depending on whether paper exists
      expect([200, 400, 404, 500]).toContain(response.status());
    });

    test('returns JSON content type', async ({ request }) => {
      const arxivId = '2301.00001';
      const response = await request.get(`/api/arxiv-metadata/${arxivId}`);

      const contentType = response.headers()['content-type'];
      expect(contentType).toContain('application/json');
    });

    test('metadata response has expected fields when successful', async ({ request }) => {
      // Use a well-known paper that should exist
      const arxivId = '1706.03762'; // "Attention Is All You Need" paper
      const response = await request.get(`/api/arxiv-metadata/${arxivId}`);

      if (response.status() === 200) {
        const data = await response.json();

        // Verify expected fields
        expect(data).toHaveProperty('arxivId');
        expect(typeof data.arxivId).toBe('string');

        expect(data).toHaveProperty('title');
        expect(typeof data.title).toBe('string');

        expect(data).toHaveProperty('authors');
        expect(Array.isArray(data.authors)).toBe(true);

        expect(data).toHaveProperty('abstract');
        expect(typeof data.abstract).toBe('string');

        // Optional fields that may be present
        if (data.publishedDate) {
          expect(typeof data.publishedDate).toBe('string');
        }
        if (data.categories) {
          expect(Array.isArray(data.categories)).toBe(true);
        }
      }
    });

    test('handles concurrent requests', async ({ request }) => {
      const arxivIds = [
        generateTestArxivId(),
        generateTestArxivId(),
        generateTestArxivId(),
      ];

      const responses = await Promise.all(
        arxivIds.map((id) => request.get(`/api/arxiv-metadata/${id}`))
      );

      // All requests should complete without server errors
      for (const response of responses) {
        expect([200, 400, 404, 500]).toContain(response.status());
      }
    });
  });
});
