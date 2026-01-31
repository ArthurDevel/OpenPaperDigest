/**
 * Admin Cumulative Daily Stats API Route
 *
 * Returns daily paper completion counts for charting.
 * - GET: Fetch cumulative daily paper statistics
 * - Requires HTTP Basic authentication
 */

import { NextRequest, NextResponse } from 'next/server';
import { adminGuard } from '@/lib/admin-auth';
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
  // Defense-in-depth: middleware handles auth, this is a fallback
  const authError = adminGuard(request);
  if (authError) return authError;

  try {
    const stats = await papersService.getCumulativeDailyStats();
    return NextResponse.json(stats);
  } catch (error) {
    console.error('Error fetching cumulative daily stats:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
