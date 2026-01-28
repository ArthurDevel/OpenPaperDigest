/**
 * Playwright Configuration for API E2E Tests
 *
 * Configures Playwright for API-only testing (no browser required).
 * - Sets up base URL for API requests
 * - Configures timeouts and retry behavior
 * - Uses global setup for environment validation
 */

import { defineConfig } from '@playwright/test';

// ============================================================================
// CONSTANTS
// ============================================================================

const BASE_URL = process.env.TEST_BASE_URL || 'http://localhost:3001';
const DEFAULT_TIMEOUT = 30000;
const RETRY_COUNT = process.env.CI ? 2 : 0;

// ============================================================================
// CONFIGURATION
// ============================================================================

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: RETRY_COUNT,
  workers: process.env.CI ? 1 : undefined,
  reporter: [['list'], ['html', { open: 'never' }]],
  timeout: DEFAULT_TIMEOUT,
  globalSetup: './tests/e2e/setup/global-setup.ts',

  use: {
    baseURL: BASE_URL,
    extraHTTPHeaders: {
      Accept: 'application/json',
    },
    trace: 'on-first-retry',
  },

  // API tests do not require browser projects
  projects: [
    {
      name: 'api',
      testMatch: /.*\.api\.test\.ts$/,
    },
  ],
});
