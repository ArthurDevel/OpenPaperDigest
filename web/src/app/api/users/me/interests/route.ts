/**
 * User Interests Clustering API Route
 *
 * Returns the authenticated user's interacted papers grouped into clusters
 * using on-the-fly k-means on paper embeddings.
 *
 * Responsibilities:
 * - GET: Authenticate user, parse maxClusters param, return clustered papers
 */

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase/server';
import { getInterestClusters } from '@/services/interests.service';
import type { InterestClustersResponse } from '@/types/interests';

// ============================================================================
// CONSTANTS
// ============================================================================

const DEFAULT_MAX_CLUSTERS = 5;
const MIN_CLUSTERS = 1;
const MAX_CLUSTERS = 10;

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
 * GET handler for interest clusters.
 * Accepts optional `maxClusters` query param (1-10, default 5).
 * @param request - The incoming request with optional maxClusters query param
 * @returns InterestClustersResponse on success, 401 if unauthenticated, 500 on error
 */
export async function GET(
  request: NextRequest
): Promise<NextResponse<InterestClustersResponse | ErrorResponse>> {
  try {
    const supabase = await createClient();
    const { data: { user }, error: authError } = await supabase.auth.getUser();

    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    // Parse and clamp maxClusters
    const rawParam = request.nextUrl.searchParams.get('maxClusters');
    let maxClusters = DEFAULT_MAX_CLUSTERS;
    if (rawParam) {
      const parsed = parseInt(rawParam, 10);
      if (!isNaN(parsed)) {
        maxClusters = Math.max(MIN_CLUSTERS, Math.min(MAX_CLUSTERS, parsed));
      }
    }

    const result = await getInterestClusters(user.id, maxClusters);

    return NextResponse.json(result);
  } catch (error) {
    console.error('Error fetching interest clusters:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
