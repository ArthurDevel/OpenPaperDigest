/**
 * Paper Markdown API Route
 *
 * Returns the raw markdown content for a paper.
 * - GET: Fetch paper markdown by UUID
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
 * GET handler for fetching a paper's markdown content.
 * @param request - The incoming Next.js request
 * @param params - Route params containing the paper UUID
 * @returns Plain text response with markdown content
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ uuid: string }> }
): Promise<NextResponse<string | ErrorResponse>> {
  try {
    const { uuid } = await params;

    if (!uuid) {
      return NextResponse.json({ error: 'Missing UUID parameter' }, { status: 400 });
    }

    const markdown = await papersService.getPaperMarkdown(uuid);

    return new NextResponse(markdown, {
      status: 200,
      headers: {
        'Content-Type': 'text/plain; charset=utf-8',
      },
    });
  } catch (error) {
    // Check for specific error messages from service
    if (error instanceof Error) {
      if (error.message.includes('not found')) {
        return NextResponse.json({ error: 'Paper not found' }, { status: 404 });
      }
      if (error.message.includes('no processed content')) {
        return NextResponse.json({ error: 'Paper has no processed content' }, { status: 404 });
      }
    }

    console.error('Error fetching paper markdown:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
