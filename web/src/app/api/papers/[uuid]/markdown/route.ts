/**
 * Paper Markdown API Route
 *
 * Returns the raw markdown content for a paper from Supabase Storage.
 * - GET: Fetch paper markdown by UUID
 */

import { NextRequest, NextResponse } from 'next/server';
import { downloadPaperMarkdown } from '@/lib/supabase/storage';

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
 * Downloads content.md from Supabase Storage.
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

    const markdown = await downloadPaperMarkdown(uuid);

    return new NextResponse(markdown, {
      status: 200,
      headers: {
        'Content-Type': 'text/plain; charset=utf-8',
      },
    });
  } catch (error) {
    if (error instanceof Error && error.message.includes('Failed to download')) {
      return NextResponse.json({ error: 'Paper content not found in storage' }, { status: 404 });
    }

    console.error('Error fetching paper markdown:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
