/**
 * Admin Authentication Guard
 *
 * Defense-in-depth check for admin API endpoints.
 * Primary authentication is handled by middleware - this is a fallback guard.
 */

import { NextRequest, NextResponse } from 'next/server';

/**
 * Simple guard check for admin routes.
 * Middleware handles the full Basic auth validation - this is a defense-in-depth check.
 *
 * @param request - The incoming Next.js request
 * @returns NextResponse with 401 if no auth header present, null if OK
 *
 * @example
 * ```ts
 * export async function GET(request: NextRequest) {
 *   const authError = adminGuard(request);
 *   if (authError) return authError;
 *   // ... admin-only logic
 * }
 * ```
 */
export function adminGuard(request: NextRequest): NextResponse<{ error: string }> | null {
  // Middleware handles full auth - this is just a safety check
  if (!request.headers.get('authorization')) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  return null;
}
