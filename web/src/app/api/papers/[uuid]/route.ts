/**
 * Full Paper JSON API Route
 *
 * Returns the full processed content JSON for a paper.
 * - GET: Fetch complete paper JSON by UUID
 */

import { NextRequest, NextResponse } from 'next/server';
import * as papersService from '@/services/papers.service';

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
 * GET handler for fetching the full paper JSON.
 * @param request - The incoming Next.js request
 * @param params - Route params containing the paper UUID
 * @returns JSON response with full paper content
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ uuid: string }> }
): Promise<NextResponse<Record<string, unknown> | ErrorResponse>> {
  try {
    const { uuid } = await params;

    if (!uuid) {
      return NextResponse.json({ error: 'Missing UUID parameter' }, { status: 400 });
    }

    const result = await papersService.getPaperJson(uuid);
    return NextResponse.json(result);
  } catch (error) {
    // Check for specific error messages from service
    if (error instanceof Error && error.message.includes('not found')) {
      return NextResponse.json({ error: 'Paper not found' }, { status: 404 });
    }

    console.error('Error fetching paper JSON:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
