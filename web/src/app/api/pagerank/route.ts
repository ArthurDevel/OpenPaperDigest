/**
 * PageRank Scatter Data API Route
 *
 * Returns scatter chart data: one item per paper with the best author
 * pagerank percentile. No authentication required.
 *
 * Responsibilities:
 * - GET /api/pagerank - returns PageRankScatterItem[]
 */

import { NextResponse } from 'next/server';
import * as pagerankService from '@/services/pagerank.service';
import type { PageRankScatterItem } from '@/services/pagerank.service';

export const dynamic = 'force-dynamic';

// ============================================================================
// ENDPOINTS
// ============================================================================

interface ErrorResponse {
  error: string;
}

/**
 * GET /api/pagerank
 * @returns Array of PageRankScatterItem objects
 */
export async function GET(): Promise<NextResponse<PageRankScatterItem[] | ErrorResponse>> {
  try {
    const data = await pagerankService.getPageRankScatterData();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Error fetching pagerank scatter data:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
