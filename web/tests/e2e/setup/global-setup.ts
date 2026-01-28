/**
 * Global Setup for E2E API Tests
 *
 * Validates test environment before running tests.
 * - Checks that required environment variables are set
 * - Verifies the server is reachable
 */

// ============================================================================
// CONSTANTS
// ============================================================================

const BASE_URL = process.env.TEST_BASE_URL || 'http://localhost:3001';
const HEALTH_ENDPOINT = '/api/health';
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1000;

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Waits for the specified number of milliseconds.
 * @param ms - Number of milliseconds to wait
 */
async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Checks if the server is reachable by calling the health endpoint.
 * @returns True if server is healthy, false otherwise
 */
async function checkServerHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${BASE_URL}${HEALTH_ENDPOINT}`);
    if (response.ok) {
      const data = await response.json();
      return data.status === 'ok';
    }
    return false;
  } catch {
    return false;
  }
}

// ============================================================================
// MAIN SETUP
// ============================================================================

/**
 * Global setup function called before all tests.
 * Validates environment and server availability.
 */
async function globalSetup(): Promise<void> {
  console.log(`\nE2E API Tests - Global Setup`);
  console.log(`Base URL: ${BASE_URL}`);

  // Log environment info
  console.log(`Admin auth configured: ${process.env.ADMIN_BASIC_PASSWORD ? 'Yes' : 'No'}`);

  // Check server health with retries
  console.log(`Checking server health...`);

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    const isHealthy = await checkServerHealth();

    if (isHealthy) {
      console.log(`Server is healthy and ready for tests.\n`);
      return;
    }

    if (attempt < MAX_RETRIES) {
      console.log(`Server not ready (attempt ${attempt}/${MAX_RETRIES}). Retrying in ${RETRY_DELAY_MS}ms...`);
      await sleep(RETRY_DELAY_MS);
    }
  }

  // Server not available after retries
  console.warn(`WARNING: Server at ${BASE_URL} is not responding.`);
  console.warn(`Tests that require a running server will fail.`);
  console.warn(`Start the server with: npm run dev\n`);
}

export default globalSetup;
