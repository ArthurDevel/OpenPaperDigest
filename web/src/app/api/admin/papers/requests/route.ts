/**
 * Admin Paper Requests API Route
 *
 * Returns all user paper requests for admin review.
 * - GET: Fetch all paper requests from all users
 * - Requires HTTP Basic authentication
 */

import { NextRequest, NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/admin-auth';
import * as usersService from '@/services/users.service';
import type { AdminRequestItem } from '@/types/user';

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
 * GET handler for fetching all paper requests from all users.
 * Requires admin authentication via HTTP Basic auth.
 * @param request - The incoming Next.js request
 * @returns JSON response with array of all admin request items
 */
export async function GET(
  request: NextRequest
): Promise<NextResponse<AdminRequestItem[] | ErrorResponse>> {
  // Verify admin authentication
  try {
    await requireAdmin(request);
  } catch (response) {
    return response as NextResponse<ErrorResponse>;
  }

  try {
    const requests = await usersService.getAllRequests();
    return NextResponse.json(requests);
  } catch (error) {
    console.error('Error fetching all paper requests:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
