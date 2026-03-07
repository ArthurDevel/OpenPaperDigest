/**
 * POST /api/papers/[uuid]/generate-summary
 *
 * Triggers on-demand summary generation for a paper that has no summary yet.
 * Returns the generated summary text, or the existing summary if one was
 * written by a concurrent request.
 *
 * Responsibilities:
 * - Validate UUID parameter
 * - Delegate to summary generation service
 * - Return structured JSON response
 */

import { NextRequest, NextResponse } from 'next/server';
import { generateSummaryForPaper } from '@/services/summary-generation.service';

// ============================================================================
// INTERFACES
// ============================================================================

interface GenerateSummaryResponse {
  summary: string;
  alreadyExisted: boolean;
}

interface ErrorResponse {
  error: string;
}

// ============================================================================
// ENDPOINT
// ============================================================================

/**
 * Generate a 5-minute summary for a paper on demand.
 * @param _request - Next.js request object (unused)
 * @param params - Route params containing paper UUID
 * @returns JSON with summary text or error
 */
export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ uuid: string }> }
): Promise<NextResponse<GenerateSummaryResponse | ErrorResponse>> {
  try {
    const { uuid } = await params;

    if (!uuid) {
      return NextResponse.json({ error: 'Paper UUID is required' }, { status: 400 });
    }

    const result = await generateSummaryForPaper(uuid);

    return NextResponse.json({
      summary: result.summary,
      alreadyExisted: result.alreadyExisted,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to generate summary';

    if (message.includes('not found') || message.includes('not available')) {
      return NextResponse.json({ error: message }, { status: 404 });
    }

    console.error('Summary generation failed:', error);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
