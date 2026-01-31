/**
 * User Requests API Route
 *
 * Manages the authenticated user's paper processing requests.
 * - GET: Retrieve all paper requests made by the user
 */

import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import * as usersService from '@/services/users.service';
import type { UserRequestItem } from '@/types/user';

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
 * GET handler for fetching user's paper requests.
 * Requires authentication.
 * @param request - The incoming Next.js request
 * @returns JSON response with array of user's paper requests
 */
export async function GET(
  request: NextRequest
): Promise<NextResponse<UserRequestItem[] | ErrorResponse>> {
  try {
    // Verify authentication
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const userId = session.user.id;
    const requests = await usersService.listRequests(userId);
    return NextResponse.json(requests);
  } catch (error) {
    console.error('Error fetching user requests:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
