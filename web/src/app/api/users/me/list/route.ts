/**
 * User List API Route
 *
 * Manages the authenticated user's paper list.
 * - GET: Retrieve all papers in user's saved list
 */

import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import * as usersService from '@/services/users.service';
import type { UserListItem } from '@/types/user';

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
 * GET handler for fetching user's paper list.
 * Requires authentication.
 * @param request - The incoming Next.js request
 * @returns JSON response with array of papers in user's list
 */
export async function GET(
  request: NextRequest
): Promise<NextResponse<UserListItem[] | ErrorResponse>> {
  try {
    // Verify authentication
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const userId = session.user.id;
    const list = await usersService.getList(userId);
    return NextResponse.json(list);
  } catch (error) {
    console.error('Error fetching user list:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
