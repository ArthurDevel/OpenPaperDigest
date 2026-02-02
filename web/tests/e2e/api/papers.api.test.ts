/**
 * API E2E Tests - Papers Minimal Endpoint
 *
 * Tests the /api/papers/minimal endpoint against the real Supabase database.
 * Created to debug 500 errors occurring when the Next.js app calls Supabase.
 *
 * Responsibilities:
 * - Verify the minimal papers list endpoint returns 200
 * - Verify response structure matches PaginatedMinimalPapers interface
 * - Test pagination parameters
 *
 * Environment Requirements:
 * - Running Next.js server on localhost:3000
 * - NEXT_PUBLIC_SUPABASE_URL: Supabase project URL
 * - NEXT_PUBLIC_SUPABASE_ANON_KEY: Supabase anonymous key
 */

import { test, expect } from '@playwright/test';

// ============================================================================
// CONSTANTS
// ============================================================================

const DEFAULT_PAGE = 1;
const DEFAULT_LIMIT = 20;

// ============================================================================
// PAPERS MINIMAL ENDPOINT TESTS
// ============================================================================

test.describe('GET /api/papers/minimal', () => {
  test('returns 200 and paginated response with default parameters', async ({ request }) => {
    const response = await request.get('/api/papers/minimal');

    // Log response details for debugging
    const status = response.status();
    console.log(`Response status: ${status}`);

    if (status !== 200) {
      const body = await response.text();
      console.log(`Response body: ${body}`);
    }

    // Primary assertion - currently failing with 500
    expect(response.status()).toBe(200);

    const body = await response.json();

    // Verify response structure matches PaginatedMinimalPapers
    expect(body).toHaveProperty('items');
    expect(body).toHaveProperty('page');
    expect(body).toHaveProperty('limit');
    expect(body).toHaveProperty('hasMore');

    // Verify types
    expect(Array.isArray(body.items)).toBe(true);
    expect(typeof body.page).toBe('number');
    expect(typeof body.limit).toBe('number');
    expect(typeof body.hasMore).toBe('boolean');

    // Verify default pagination values
    expect(body.page).toBe(DEFAULT_PAGE);
    expect(body.limit).toBe(DEFAULT_LIMIT);
  });

  test('returns paginated response with custom page parameter', async ({ request }) => {
    const response = await request.get('/api/papers/minimal?page=2');

    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body.page).toBe(2);
  });

  test('returns paginated response with custom limit parameter', async ({ request }) => {
    const response = await request.get('/api/papers/minimal?limit=5');

    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body.limit).toBe(5);
    expect(body.items.length).toBeLessThanOrEqual(5);
  });

  test('returns 400 for invalid page parameter', async ({ request }) => {
    const response = await request.get('/api/papers/minimal?page=0');

    expect(response.status()).toBe(400);

    const body = await response.json();
    expect(body).toHaveProperty('error');
    expect(body.error).toBe('Invalid page parameter');
  });

  test('returns 400 for invalid limit parameter (too high)', async ({ request }) => {
    const response = await request.get('/api/papers/minimal?limit=101');

    expect(response.status()).toBe(400);

    const body = await response.json();
    expect(body).toHaveProperty('error');
    expect(body.error).toBe('Invalid limit parameter (must be 1-100)');
  });

  test('returns 400 for invalid limit parameter (zero)', async ({ request }) => {
    const response = await request.get('/api/papers/minimal?limit=0');

    expect(response.status()).toBe(400);

    const body = await response.json();
    expect(body).toHaveProperty('error');
    expect(body.error).toBe('Invalid limit parameter (must be 1-100)');
  });

  test('items have correct MinimalPaper structure when data exists', async ({ request }) => {
    const response = await request.get('/api/papers/minimal?limit=1');

    expect(response.status()).toBe(200);

    const body = await response.json();

    // Only check item structure if there are items
    if (body.items.length > 0) {
      const item = body.items[0];

      // Required fields
      expect(item).toHaveProperty('paperUuid');
      expect(typeof item.paperUuid).toBe('string');

      // Nullable fields - verify they exist (can be null)
      expect('title' in item).toBe(true);
      expect('authors' in item).toBe(true);
      expect('thumbnailDataUrl' in item).toBe(true);
      expect('slug' in item).toBe(true);
      expect('thumbnailUrl' in item).toBe(true);
    }
  });
});
