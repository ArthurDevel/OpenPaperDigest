/**
 * Admin Papers List API Route
 *
 * Returns all papers with full details for admin management.
 * - GET: Fetch all papers (includes all statuses, not just completed)
 * - Requires HTTP Basic authentication
 */

import { NextRequest, NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/admin-auth';
import * as papersService from '@/services/papers.service';
import type { JobDbStatus } from '@/types/paper';

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
 * GET handler for fetching all papers (admin).
 * Supports optional status filter and limit query parameters.
 * @param request - The incoming Next.js request
 * @returns JSON response with array of paper job status objects
 */
export async function GET(
  request: NextRequest
): Promise<NextResponse<JobDbStatus[] | ErrorResponse>> {
  // Verify admin authentication
  try {
    await requireAdmin(request);
  } catch (response) {
    return response as NextResponse<ErrorResponse>;
  }

  try {
    // Parse query parameters
    const { searchParams } = new URL(request.url);
    const status = searchParams.get('status') ?? undefined;
    const limitParam = searchParams.get('limit');
    const limit = limitParam ? parseInt(limitParam, 10) : 500;

    // Validate limit
    if (isNaN(limit) || limit < 1 || limit > 10000) {
      return NextResponse.json(
        { error: 'Invalid limit parameter. Must be between 1 and 10000.' },
        { status: 400 }
      );
    }

    const papers = await papersService.listAllPapers(status, limit);
    return NextResponse.json(papers);
  } catch (error) {
    console.error('Error fetching papers for admin:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
