/**
 * Count Papers Since API Route
 *
 * Returns the count of completed papers since a given timestamp.
 * - GET: Count papers completed after the specified timestamp
 */

import { NextRequest, NextResponse } from 'next/server';
import * as papersService from '@/services/papers.service';

// ============================================================================
// TYPES
// ============================================================================

interface CountResponse {
  count: number;
}

interface ErrorResponse {
  error: string;
}

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * GET handler for counting papers since a timestamp.
 * @param request - The incoming Next.js request with 'since' query param
 * @returns JSON response with the count
 */
export async function GET(request: NextRequest): Promise<NextResponse<CountResponse | ErrorResponse>> {
  try {
    const searchParams = request.nextUrl.searchParams;
    const sinceParam = searchParams.get('since');

    if (!sinceParam) {
      return NextResponse.json({ error: 'Missing required parameter: since' }, { status: 400 });
    }

    // Parse the ISO timestamp
    const since = new Date(sinceParam);
    if (isNaN(since.getTime())) {
      return NextResponse.json({ error: 'Invalid timestamp format. Use ISO 8601 format.' }, { status: 400 });
    }

    const count = await papersService.countPapersSince(since);
    return NextResponse.json({ count });
  } catch (error) {
    console.error('Error counting papers since timestamp:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
