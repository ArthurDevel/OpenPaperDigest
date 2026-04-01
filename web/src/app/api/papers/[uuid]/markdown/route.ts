/**
 * Paper Markdown API Route
 *
 * Returns the raw markdown content for a paper from Supabase Storage.
 * Note: v2 (PDF-direct) papers return an empty string since they have no content.md.
 * - GET: Fetch paper markdown by UUID
 */

import { NextRequest, NextResponse } from 'next/server';
// COMMENTED OUT: "Copy Full Document" depends on content.md which v2 pipeline papers don't have.
// This was too expensive to regenerate for v2. Bring back once we have an affordable alternative.
// import { downloadPaperMarkdown } from '@/lib/supabase/storage';

// ============================================================================
// TYPES
// ============================================================================

interface ErrorResponse {
  error: string;
}

// ============================================================================
// MAIN HANDLERS
// ============================================================================

// COMMENTED OUT: "Copy Full Document" depends on content.md which v2 pipeline papers don't have.
// This was too expensive to regenerate for v2. Bring back once we have an affordable alternative.
//
// /**
//  * GET handler for fetching a paper's markdown content.
//  * Downloads content.md from Supabase Storage.
//  * @param request - The incoming Next.js request
//  * @param params - Route params containing the paper UUID
//  * @returns Plain text response with markdown content
//  */
// export async function GET(
//   request: NextRequest,
//   { params }: { params: Promise<{ uuid: string }> }
// ): Promise<NextResponse<string | ErrorResponse>> {
//   try {
//     const { uuid } = await params;
//
//     if (!uuid) {
//       return NextResponse.json({ error: 'Missing UUID parameter' }, { status: 400 });
//     }
//
//     const markdown = await downloadPaperMarkdown(uuid);
//
//     return new NextResponse(markdown, {
//       status: 200,
//       headers: {
//         'Content-Type': 'text/plain; charset=utf-8',
//       },
//     });
//   } catch (error) {
//     if (error instanceof Error && error.message.includes('Failed to download')) {
//       return NextResponse.json({ error: 'Paper content not found in storage' }, { status: 404 });
//     }
//
//     console.error('Error fetching paper markdown:', error);
//     return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
//   }
// }

export async function GET(
  _request: NextRequest,
  _context: { params: Promise<{ uuid: string }> }
): Promise<NextResponse<ErrorResponse>> {
  return NextResponse.json(
    { error: 'Markdown endpoint temporarily disabled - v2 papers have no content.md' },
    { status: 410 }
  );
}
