/**
 * Health Check API Integration Tests
 *
 * Tests for the health check endpoint.
 * - GET /api/health returns 200 with { status: "ok" }
 */

import { describe, it, expect } from 'vitest';
import { testApiHandler } from 'next-test-api-route-handler';
import * as appHandler from '@/app/api/health/route';

// ============================================================================
// TESTS
// ============================================================================

describe('Health API', () => {
  describe('GET /api/health', () => {
    it('returns 200 with status ok', async () => {
      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const data = await response.json();
          expect(data).toEqual({ status: 'ok' });
        },
      });
    });

    it('returns JSON content type', async () => {
      await testApiHandler({
        appHandler,
        test: async ({ fetch }) => {
          const response = await fetch({ method: 'GET' });

          expect(response.status).toBe(200);

          const contentType = response.headers.get('content-type');
          expect(contentType).toContain('application/json');
        },
      });
    });
  });
});
