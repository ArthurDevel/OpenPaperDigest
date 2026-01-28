/**
 * Admin Paper Processing Metrics API Route
 *
 * Returns detailed processing metrics for a paper (AI costs, timing).
 * - GET: Fetch processing metrics for a specific paper
 * - Requires HTTP Basic authentication
 */

import { NextRequest, NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/admin-auth';
import * as papersService from '@/services/papers.service';
import type { ProcessingMetrics } from '@/types/paper';

// ============================================================================
// TYPES
// ============================================================================

interface ErrorResponse {
  error: string;
}

interface RouteParams {
  params: Promise<{ uuid: string }>;
}

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * GET handler for fetching paper processing metrics.
 * Returns cost, timing, and status information for admin analysis.
 * @param request - The incoming Next.js request
 * @param context - Route context containing the paper UUID
 * @returns JSON response with processing metrics or error
 */
export async function GET(
  request: NextRequest,
  context: RouteParams
): Promise<NextResponse<ProcessingMetrics | ErrorResponse>> {
  // Verify admin authentication
  try {
    await requireAdmin(request);
  } catch (response) {
    return response as NextResponse<ErrorResponse>;
  }

  try {
    const { uuid } = await context.params;

    // Validate UUID format
    if (!uuid || typeof uuid !== 'string') {
      return NextResponse.json({ error: 'Invalid paper UUID' }, { status: 400 });
    }

    const metrics = await papersService.getProcessingMetricsAdmin(uuid);
    return NextResponse.json(metrics);
  } catch (error) {
    // Handle known errors
    if (error instanceof Error && error.message.includes('not found')) {
      return NextResponse.json({ error: 'Paper not found' }, { status: 404 });
    }

    console.error('Error fetching processing metrics:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
