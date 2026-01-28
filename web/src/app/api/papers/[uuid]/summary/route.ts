/**
 * Paper Summary API Route
 *
 * Returns a lightweight summary for a paper.
 * - GET: Fetch paper summary by UUID
 */

import { NextRequest, NextResponse } from 'next/server';
import * as papersService from '@/services/papers.service';
import type { PaperSummary } from '@/types/paper';

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
 * GET handler for fetching a paper's summary.
 * @param request - The incoming Next.js request
 * @param params - Route params containing the paper UUID
 * @returns JSON response with paper summary
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ uuid: string }> }
): Promise<NextResponse<PaperSummary | ErrorResponse>> {
  try {
    const { uuid } = await params;

    if (!uuid) {
      return NextResponse.json({ error: 'Missing UUID parameter' }, { status: 400 });
    }

    const result = await papersService.getPaperSummary(uuid);
    return NextResponse.json(result);
  } catch (error) {
    // Check for specific error messages from service
    if (error instanceof Error && error.message.includes('not found')) {
      return NextResponse.json({ error: 'Paper not found' }, { status: 404 });
    }

    console.error('Error fetching paper summary:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
