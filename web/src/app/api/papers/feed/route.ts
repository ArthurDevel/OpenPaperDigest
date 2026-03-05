/**
 * Feed API Route
 *
 * Returns a ranked, personalized feed of papers. Uses POST because the request
 * body includes an exclude list of already-shown paper UUIDs.
 *
 * Responsibilities:
 * - Authenticate the user (anonymous or permanent) from Supabase session
 * - Parse FeedRequest from the request body
 * - Call getRankedFeed and return FeedResponse
 * - Handle unauthenticated users gracefully (cold-start feed)
 */

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase/server';
import { getRankedFeed } from '@/services/feed.service';
import type { FeedRequest, FeedResponse } from '@/types/recommendation';

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
 * POST handler for the ranked feed endpoint.
 * Accepts FeedRequest body and returns FeedResponse.
 * Handles unauthenticated users by passing null userId (cold-start feed).
 * @param request - The incoming request with FeedRequest body
 * @returns FeedResponse on success, error on failure
 */
export async function POST(
  request: NextRequest
): Promise<NextResponse<FeedResponse | ErrorResponse>> {
  try {
    // Get user from session (may be null for unauthenticated visitors)
    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();

    // Parse request body
    const body = (await request.json()) as FeedRequest;
    const page = body.page ?? 1;
    const limit = body.limit ?? 20;
    const excludePaperUuids = body.excludePaperUuids ?? [];

    const feed = await getRankedFeed(page, limit, excludePaperUuids, user?.id ?? null);

    return NextResponse.json(feed);
  } catch (error) {
    console.error('Error fetching feed:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
