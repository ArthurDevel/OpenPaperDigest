/**
 * Admin Users List API Route
 *
 * Returns all users with activity counts for admin management.
 * - GET: Fetch all users with saved papers and requests counts
 * - Requires HTTP Basic authentication (middleware + fallback guard)
 */

import { NextRequest, NextResponse } from 'next/server';
import { adminGuard } from '@/lib/admin-auth';
import * as usersService from '@/services/users.service';
import type { AdminUserItem } from '@/types/user';

// ============================================================================
// TYPES
// ============================================================================

interface ErrorResponse {
  error: string;
}

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * GET handler for fetching all users (admin).
 * @param request - The incoming Next.js request
 * @returns JSON response with array of admin user items
 */
export async function GET(
  request: NextRequest
): Promise<NextResponse<AdminUserItem[] | ErrorResponse>> {
  const authError = adminGuard(request);
  if (authError) return authError;

  try {
    const users = await usersService.listAllUsers();
    return NextResponse.json(users);
  } catch (error) {
    console.error('Error fetching users for admin:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
