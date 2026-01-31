/**
 * API E2E Tests - Authentication
 *
 * Tests that protected API endpoints correctly reject unauthenticated requests.
 *
 * Responsibilities:
 * - Verify 401 responses for unauthenticated requests
 * - Test all protected user API routes
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

const TEST_UUID = '00000000-0000-0000-0000-000000000000';

// ============================================================================
// PROTECTED API ROUTES
// ============================================================================

test.describe('Protected API Routes - Unauthenticated Access', () => {
  test('GET /api/users/me/list returns 401 without auth cookies', async ({ request }) => {
    const response = await request.get('/api/users/me/list');

    expect(response.status()).toBe(401);

    const body = await response.json();
    expect(body).toHaveProperty('error');
    expect(body.error).toBe('Unauthorized');
  });

  test('GET /api/users/me/requests returns 401 without auth cookies', async ({ request }) => {
    const response = await request.get('/api/users/me/requests');

    expect(response.status()).toBe(401);

    const body = await response.json();
    expect(body).toHaveProperty('error');
    expect(body.error).toBe('Unauthorized');
  });

  test('GET /api/users/me/list/[uuid] returns 401 without auth cookies', async ({ request }) => {
    const response = await request.get(`/api/users/me/list/${TEST_UUID}`);

    expect(response.status()).toBe(401);

    const body = await response.json();
    expect(body).toHaveProperty('error');
    expect(body.error).toBe('Unauthorized');
  });

  test('POST /api/users/me/list/[uuid] returns 401 without auth cookies', async ({ request }) => {
    const response = await request.post(`/api/users/me/list/${TEST_UUID}`);

    expect(response.status()).toBe(401);

    const body = await response.json();
    expect(body).toHaveProperty('error');
    expect(body.error).toBe('Unauthorized');
  });

  test('DELETE /api/users/me/list/[uuid] returns 401 without auth cookies', async ({ request }) => {
    const response = await request.delete(`/api/users/me/list/${TEST_UUID}`);

    expect(response.status()).toBe(401);

    const body = await response.json();
    expect(body).toHaveProperty('error');
    expect(body.error).toBe('Unauthorized');
  });
});
