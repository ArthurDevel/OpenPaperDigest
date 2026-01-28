/**
 * Admin Authentication Helper
 *
 * Provides HTTP Basic authentication for admin API endpoints.
 * - Validates credentials against environment-configured password
 * - Uses timing-safe comparison to prevent timing attacks
 * - Throws appropriate HTTP responses on authentication failure
 */

import { NextRequest } from 'next/server';
import { env } from './env';

// ============================================================================
// CONSTANTS
// ============================================================================

const ADMIN_USERNAME = 'admin';
const AUTH_REALM = 'Management';

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Performs a timing-safe comparison of two strings.
 * Both strings are padded/truncated to the same length before comparison
 * to ensure constant-time execution regardless of input.
 *
 * @param a - First string to compare
 * @param b - Second string to compare
 * @returns True if strings are equal, false otherwise
 */
function timingSafeEqual(a: string, b: string): boolean {
  const encoder = new TextEncoder();
  const aBytes = encoder.encode(a);
  const bBytes = encoder.encode(b);

  // If lengths differ, still do comparison to maintain constant time
  // but ensure result is false
  const maxLen = Math.max(aBytes.length, bBytes.length);
  const aPadded = new Uint8Array(maxLen);
  const bPadded = new Uint8Array(maxLen);

  aPadded.set(aBytes);
  bPadded.set(bBytes);

  // Use crypto.timingSafeEqual if available (Node.js runtime)
  if (typeof crypto !== 'undefined' && 'timingSafeEqual' in crypto.subtle === false) {
    // Fallback: manual XOR comparison for edge runtime
    let result = aBytes.length === bBytes.length ? 0 : 1;
    for (let i = 0; i < maxLen; i++) {
      result |= aPadded[i] ^ bPadded[i];
    }
    return result === 0;
  }

  // Node.js crypto module timing-safe comparison
  const cryptoModule = require('crypto');
  if (aBytes.length !== bBytes.length) {
    // Compare against self to maintain timing, then return false
    cryptoModule.timingSafeEqual(aBytes, aBytes);
    return false;
  }
  return cryptoModule.timingSafeEqual(aBytes, bBytes);
}

// ============================================================================
// MAIN EXPORTS
// ============================================================================

/**
 * Validates HTTP Basic authentication for admin endpoints.
 * Expects credentials in the format: "admin:<ADMIN_BASIC_PASSWORD>"
 *
 * @param request - The incoming Next.js request
 * @throws Response with 401 status if authentication fails
 *
 * @example
 * ```ts
 * export async function GET(request: NextRequest) {
 *   await requireAdmin(request);
 *   // ... admin-only logic
 * }
 * ```
 */
export async function requireAdmin(request: NextRequest): Promise<void> {
  const authHeader = request.headers.get('authorization');

  // Check for Basic auth header
  if (!authHeader || !authHeader.startsWith('Basic ')) {
    throw new Response('Unauthorized', {
      status: 401,
      headers: { 'WWW-Authenticate': `Basic realm="${AUTH_REALM}"` },
    });
  }

  // Decode Base64 credentials
  const base64Credentials = authHeader.slice(6); // Remove "Basic " prefix
  let credentials: string;
  try {
    credentials = Buffer.from(base64Credentials, 'base64').toString('utf-8');
  } catch {
    throw new Response('Unauthorized', {
      status: 401,
      headers: { 'WWW-Authenticate': `Basic realm="${AUTH_REALM}"` },
    });
  }

  // Split into username:password
  const colonIndex = credentials.indexOf(':');
  if (colonIndex === -1) {
    throw new Response('Unauthorized', { status: 401 });
  }

  const username = credentials.slice(0, colonIndex);
  const password = credentials.slice(colonIndex + 1);

  // Validate credentials with timing-safe comparison
  const usernameValid = timingSafeEqual(username, ADMIN_USERNAME);
  const passwordValid = timingSafeEqual(password, env.ADMIN_BASIC_PASSWORD);

  if (!usernameValid || !passwordValid) {
    throw new Response('Unauthorized', { status: 401 });
  }

  // Authentication successful - void return
}
