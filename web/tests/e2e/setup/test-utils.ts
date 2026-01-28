/**
 * Test Utilities for E2E API Tests
 *
 * Provides helper functions for common test operations.
 * - Admin HTTP Basic auth header generation
 * - User auth header generation (placeholder for BetterAuth)
 * - Common test data factories
 */

// ============================================================================
// CONSTANTS
// ============================================================================

const ADMIN_USERNAME = 'admin';
const DEFAULT_ADMIN_PASSWORD = 'testpassword';

// ============================================================================
// AUTH HELPERS
// ============================================================================

/**
 * Creates HTTP Basic auth header for admin endpoints.
 * Uses ADMIN_BASIC_PASSWORD environment variable or default test password.
 * @returns Authorization header value
 */
export function getAdminAuthHeader(): string {
  const password = process.env.ADMIN_BASIC_PASSWORD || DEFAULT_ADMIN_PASSWORD;
  const credentials = Buffer.from(`${ADMIN_USERNAME}:${password}`).toString('base64');
  return `Basic ${credentials}`;
}

/**
 * Creates invalid HTTP Basic auth header for testing auth failures.
 * @returns Authorization header with wrong credentials
 */
export function getInvalidAdminAuthHeader(): string {
  const credentials = Buffer.from('admin:wrongpassword').toString('base64');
  return `Basic ${credentials}`;
}

/**
 * Creates headers object with admin authentication.
 * @returns Headers object with Authorization header
 */
export function getAdminHeaders(): Record<string, string> {
  return {
    Authorization: getAdminAuthHeader(),
  };
}

// ============================================================================
// TEST DATA FACTORIES
// ============================================================================

/**
 * Generates a random UUID for testing.
 * @returns A random UUID string
 */
export function generateTestUuid(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Generates a test arXiv ID.
 * @returns A valid arXiv ID format string
 */
export function generateTestArxivId(): string {
  const year = Math.floor(Math.random() * 10) + 20; // 20-29
  const month = String(Math.floor(Math.random() * 12) + 1).padStart(2, '0');
  const number = String(Math.floor(Math.random() * 99999)).padStart(5, '0');
  return `${year}${month}.${number}`;
}

/**
 * Creates a test paper import payload.
 * @param uuid - Optional UUID to use
 * @returns Paper JSON object for import
 */
export function createTestPaperPayload(uuid?: string): Record<string, unknown> {
  const paperUuid = uuid || generateTestUuid();
  return {
    paper_uuid: paperUuid,
    arxiv_id: generateTestArxivId(),
    title: 'Test Paper Title',
    authors: ['Test Author 1', 'Test Author 2'],
    abstract: 'This is a test abstract for the paper.',
    source_url: 'https://arxiv.org/abs/2301.00001',
    summary: {
      overview: 'Test overview',
      key_points: ['Point 1', 'Point 2'],
    },
  };
}

// ============================================================================
// RESPONSE VALIDATORS
// ============================================================================

/**
 * Checks if a response body contains an error field.
 * @param body - Response body to check
 * @returns True if body has error field
 */
export function isErrorResponse(body: unknown): body is { error: string } {
  return (
    typeof body === 'object' &&
    body !== null &&
    'error' in body &&
    typeof (body as Record<string, unknown>).error === 'string'
  );
}

/**
 * Checks if a value is a valid UUID format.
 * @param value - Value to check
 * @returns True if value is a valid UUID
 */
export function isValidUuid(value: unknown): boolean {
  if (typeof value !== 'string') return false;
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  return uuidRegex.test(value);
}

/**
 * Checks if a value is a valid ISO date string.
 * @param value - Value to check
 * @returns True if value is a valid ISO date
 */
export function isValidIsoDate(value: unknown): boolean {
  if (typeof value !== 'string') return false;
  const date = new Date(value);
  return !isNaN(date.getTime());
}
