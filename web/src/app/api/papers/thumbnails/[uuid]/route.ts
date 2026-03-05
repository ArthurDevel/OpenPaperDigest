/**
 * Paper Thumbnail API Route
 *
 * Redirects to a signed Supabase Storage URL for a paper's thumbnail.
 * - GET: Returns HTTP 302 redirect to signed storage thumbnail URL
 */

import { NextRequest, NextResponse } from 'next/server';
import { getPaperThumbnailUrl } from '@/lib/supabase/storage';

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
 * Redirects to a signed Supabase Storage URL.
 * @param request - The incoming Next.js request
 * @param params - Route params containing the paper UUID
 * @returns HTTP 302 redirect to the signed storage thumbnail URL
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ uuid: string }> }
): Promise<NextResponse> {
  try {
    const { uuid } = await params;

    if (!uuid) {
      return NextResponse.json({ error: 'Missing UUID parameter' }, { status: 400 });
    }

    const thumbnailUrl = await getPaperThumbnailUrl(uuid);
    if (!thumbnailUrl) {
      return NextResponse.json({ error: 'Thumbnail not found' }, { status: 404 });
    }
    return NextResponse.redirect(thumbnailUrl, 302);
  } catch (error) {
    console.error('Error redirecting to thumbnail:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
