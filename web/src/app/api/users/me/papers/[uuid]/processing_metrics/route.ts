/**
 * User Paper Processing Metrics API Route
 *
 * Returns processing metrics for a paper initiated by the authenticated user.
 * - GET: Fetch processing metrics (cost, timing, status) for a user's paper
 */

import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import * as usersService from '@/services/users.service';
import type { ProcessingMetrics } from '@/types/paper';

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
 * GET handler for fetching processing metrics for a user's paper.
 * Requires authentication. User must have initiated the paper.
 * @param request - The incoming Next.js request
 * @param params - Route params containing the paper UUID
 * @returns JSON response with processing metrics
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ uuid: string }> }
): Promise<NextResponse<ProcessingMetrics | ErrorResponse>> {
  try {
    // Verify authentication
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { uuid } = await params;
    if (!uuid) {
      return NextResponse.json({ error: 'Missing UUID parameter' }, { status: 400 });
    }

    const userId = session.user.id;
    const metrics = await usersService.getProcessingMetrics(userId, uuid);

    if (!metrics) {
      return NextResponse.json(
        { error: 'Paper not found or not initiated by user' },
        { status: 404 }
      );
    }

    return NextResponse.json(metrics);
  } catch (error) {
    console.error('Error fetching processing metrics:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
