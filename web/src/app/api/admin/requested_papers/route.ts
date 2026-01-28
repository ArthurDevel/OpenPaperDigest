/**
 * Admin Requested Papers List API Route
 *
 * Returns aggregated list of user paper requests for admin review.
 * - GET: Fetch all paper requests grouped by arXiv ID with counts
 * - Requires HTTP Basic authentication
 *
 * Note: This endpoint exists at /admin/requested_papers for backwards
 * compatibility with the Python admin endpoints.
 */

import { NextRequest, NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/admin-auth';
import * as usersService from '@/services/users.service';
import type { AggregatedRequestItem } from '@/types/user';

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
 * GET handler for fetching aggregated paper requests.
 * Returns requests grouped by arXiv ID with request counts.
 * @param request - The incoming Next.js request
 * @returns JSON response with array of aggregated request items
 */
export async function GET(
  request: NextRequest
): Promise<NextResponse<AggregatedRequestItem[] | ErrorResponse>> {
  // Verify admin authentication
  try {
    await requireAdmin(request);
  } catch (response) {
    return response as NextResponse<ErrorResponse>;
  }

  try {
    const requests = await usersService.getAggregatedRequests();
    return NextResponse.json(requests);
  } catch (error) {
    console.error('Error fetching aggregated paper requests:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
