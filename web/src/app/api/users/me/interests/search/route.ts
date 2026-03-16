/**
 * Interest Search API Route
 *
 * Accepts a centroid embedding and returns papers similar to it,
 * excluding papers the user has already interacted with.
 * Returns items in MinimalPaper format compatible with PaperCard.
 *
 * Responsibilities:
 * - POST: Authenticate user, validate embedding, return similar papers
 */

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase/server';
import { searchSimilarPapers } from '@/services/interests.service';
import type { MinimalPaper } from '@/types/paper';

// ============================================================================
// CONSTANTS
// ============================================================================

const DEFAULT_LIMIT = 20;
const MAX_LIMIT = 50;

// ============================================================================
// TYPES
// ============================================================================

interface SearchResponse {
  items: MinimalPaper[];
}

interface ErrorResponse {
  error: string;
}

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * POST handler for interest-based paper search.
 * Accepts a centroid embedding and optional limit in the request body.
 * @param request - The incoming request with { embedding: number[], limit?: number }
 * @returns { items: MinimalPaper[] } on success, 400/401/500 on error
 */
export async function POST(
  request: NextRequest
): Promise<NextResponse<SearchResponse | ErrorResponse>> {
  try {
    const supabase = await createClient();
    const { data: { user }, error: authError } = await supabase.auth.getUser();

    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await request.json();

    // Validate embedding
    if (!Array.isArray(body.embedding) || body.embedding.length === 0) {
      return NextResponse.json({ error: 'Missing or invalid embedding' }, { status: 400 });
    }

    // Parse and clamp limit
    let limit = DEFAULT_LIMIT;
    if (typeof body.limit === 'number' && body.limit > 0) {
      limit = Math.min(body.limit, MAX_LIMIT);
    }

    const items = await searchSimilarPapers(user.id, body.embedding, limit);

    return NextResponse.json({ items });
  } catch (error) {
    console.error('Error searching similar papers:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
