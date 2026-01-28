/**
 * Admin Cumulative Daily Stats API Route
 *
 * Returns daily paper completion counts for charting.
 * - GET: Fetch cumulative daily paper statistics
 * - Requires HTTP Basic authentication
 */

import { NextRequest, NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/admin-auth';
import * as papersService from '@/services/papers.service';
import type { CumulativeDailyItem } from '@/services/papers.service';

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
 * GET handler for fetching cumulative daily paper statistics.
 * Returns daily counts from first paper to today, including status breakdowns.
 * @param request - The incoming Next.js request
 * @returns JSON response with array of daily statistics
 */
export async function GET(
  request: NextRequest
): Promise<NextResponse<CumulativeDailyItem[] | ErrorResponse>> {
  // Verify admin authentication
  try {
    await requireAdmin(request);
  } catch (response) {
    return response as NextResponse<ErrorResponse>;
  }

  try {
    const stats = await papersService.getCumulativeDailyStats();
    return NextResponse.json(stats);
  } catch (error) {
    console.error('Error fetching cumulative daily stats:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
