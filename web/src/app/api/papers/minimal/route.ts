/**
 * Minimal Papers List API Route
 *
 * Returns a paginated list of papers with minimal fields for display.
 * - GET: Fetch paginated minimal papers list
 */

import { NextRequest, NextResponse } from 'next/server';
import * as papersService from '@/services/papers.service';
import type { PaginatedMinimalPapers } from '@/types/paper';

// ============================================================================
// CONSTANTS
// ============================================================================

const DEFAULT_PAGE = 1;
const DEFAULT_LIMIT = 20;

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * GET handler for fetching a paginated list of minimal papers.
 * @param request - The incoming Next.js request
 * @returns JSON response with paginated minimal papers
 */
export async function GET(request: NextRequest): Promise<NextResponse<PaginatedMinimalPapers | { error: string }>> {
  try {
    const searchParams = request.nextUrl.searchParams;
    const page = parseInt(searchParams.get('page') ?? String(DEFAULT_PAGE), 10);
    const limit = parseInt(searchParams.get('limit') ?? String(DEFAULT_LIMIT), 10);

    // Validate pagination params
    if (isNaN(page) || page < 1) {
      return NextResponse.json({ error: 'Invalid page parameter' }, { status: 400 });
    }
    if (isNaN(limit) || limit < 1 || limit > 100) {
      return NextResponse.json({ error: 'Invalid limit parameter (must be 1-100)' }, { status: 400 });
    }

    const result = await papersService.listMinimalPapers(page, limit);
    return NextResponse.json(result);
  } catch (error) {
    console.error('Error fetching minimal papers:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
