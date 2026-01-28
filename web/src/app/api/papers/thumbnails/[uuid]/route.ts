/**
 * Paper Thumbnail API Route
 *
 * Returns the thumbnail image for a paper.
 * - GET: Fetch thumbnail binary image with aggressive caching
 */

import { NextRequest, NextResponse } from 'next/server';
import * as papersService from '@/services/papers.service';

// ============================================================================
// CONSTANTS
// ============================================================================

// Cache for 1 year (immutable content)
const CACHE_CONTROL = 'public, max-age=31536000, immutable';

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
 * GET handler for fetching a paper's thumbnail image.
 * @param request - The incoming Next.js request
 * @param params - Route params containing the paper UUID
 * @returns Binary image response with appropriate Content-Type and caching
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ uuid: string }> }
): Promise<NextResponse<Buffer | ErrorResponse>> {
  try {
    const { uuid } = await params;

    if (!uuid) {
      return NextResponse.json({ error: 'Missing UUID parameter' }, { status: 400 });
    }

    const { data, mediaType } = await papersService.getThumbnail(uuid);

    return new NextResponse(data, {
      status: 200,
      headers: {
        'Content-Type': mediaType,
        'Cache-Control': CACHE_CONTROL,
      },
    });
  } catch (error) {
    // Check for specific error messages from service
    if (error instanceof Error) {
      if (error.message.includes('not found')) {
        return NextResponse.json({ error: 'Paper not found' }, { status: 404 });
      }
      if (error.message.includes('no thumbnail')) {
        return NextResponse.json({ error: 'Paper has no thumbnail' }, { status: 404 });
      }
    }

    console.error('Error fetching thumbnail:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
