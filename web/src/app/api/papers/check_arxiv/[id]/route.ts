/**
 * Check ArXiv Paper API Route
 *
 * Checks if an arXiv paper exists and has been processed.
 * - GET: Check if arXiv paper exists by ID or URL
 */

import { NextRequest, NextResponse } from 'next/server';
import * as papersService from '@/services/papers.service';
import type { CheckArxivResponse } from '@/types/paper';

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
 * GET handler for checking if an arXiv paper exists.
 * @param request - The incoming Next.js request
 * @param params - Route params containing the arXiv ID
 * @returns JSON response with exists flag and viewer URL
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
): Promise<NextResponse<CheckArxivResponse | ErrorResponse>> {
  try {
    const { id } = await params;

    if (!id) {
      return NextResponse.json({ error: 'Missing arXiv ID parameter' }, { status: 400 });
    }

    // Decode the ID in case it was URL-encoded (for URLs containing slashes)
    const decodedId = decodeURIComponent(id);

    const result = await papersService.checkArxivExists(decodedId);
    return NextResponse.json(result);
  } catch (error) {
    console.error('Error checking arXiv paper:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
