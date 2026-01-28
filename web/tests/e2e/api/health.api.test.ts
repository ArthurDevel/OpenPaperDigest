/**
 * Health Check API E2E Tests
 *
 * Tests for the health check endpoints.
 * - GET /api/health returns 200 with { status: "ok" }
 * - GET /health returns 200 (via rewrite)
 */

import { test, expect } from '@playwright/test';

// ============================================================================
// TESTS
// ============================================================================

test.describe('Health API', () => {
  test.describe('GET /api/health', () => {
    test('returns 200 with status ok', async ({ request }) => {
      const response = await request.get('/api/health');

      expect(response.status()).toBe(200);

      const data = await response.json();
      expect(data).toEqual({ status: 'ok' });
    });

    test('returns JSON content type', async ({ request }) => {
      const response = await request.get('/api/health');

      expect(response.status()).toBe(200);

      const contentType = response.headers()['content-type'];
      expect(contentType).toContain('application/json');
    });
  });

  test.describe('GET /health (rewrite)', () => {
    test('returns 200 with status ok via rewrite', async ({ request }) => {
      const response = await request.get('/health');

      expect(response.status()).toBe(200);

      const data = await response.json();
      expect(data).toEqual({ status: 'ok' });
    });
  });
});
