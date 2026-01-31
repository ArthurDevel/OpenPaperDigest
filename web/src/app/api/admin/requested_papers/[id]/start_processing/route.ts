/**
 * Admin Start Processing Paper Request API Route
 *
 * Starts processing a requested paper by creating a paper record.
 * - POST: Create paper record for an arXiv ID to begin processing
 * - Requires HTTP Basic authentication
 *
 * Note: The [id] parameter is the arXiv ID (or URL), not a numeric ID.
 * This matches the Python admin endpoint behavior.
 */

import { NextRequest, NextResponse } from 'next/server';
import { adminGuard } from '@/lib/admin-auth';
import { normalizeId } from '@/lib/arxiv';
import * as usersService from '@/services/users.service';
import type { StartProcessingResponse } from '@/types/user';

// ============================================================================
// TYPES
// ============================================================================

interface ErrorResponse {
  error: string;
}

interface RouteParams {
  params: Promise<{ id: string }>;
}

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * POST handler for starting paper processing from a request.
 * Creates a paper record if one doesn't exist for the arXiv ID.
 * @param request - The incoming Next.js request
 * @param context - Route context containing the arXiv ID or URL
 * @returns JSON response with paper UUID and status
 */
export async function POST(
  request: NextRequest,
  context: RouteParams
): Promise<NextResponse<StartProcessingResponse | ErrorResponse>> {
  // Defense-in-depth: middleware handles auth, this is a fallback
  const authError = adminGuard(request);
  if (authError) return authError;

  try {
    const { id: arxivIdOrUrl } = await context.params;

    // Validate input
    if (!arxivIdOrUrl || typeof arxivIdOrUrl !== 'string') {
      return NextResponse.json({ error: 'Invalid arXiv ID or URL' }, { status: 400 });
    }

    // Normalize the arXiv ID
    let arxivId: string;
    try {
      const normalized = normalizeId(decodeURIComponent(arxivIdOrUrl));
      arxivId = normalized.arxivId;
    } catch {
      return NextResponse.json({ error: 'Invalid arXiv ID or URL' }, { status: 400 });
    }

    // Start processing (creates paper record if needed)
    const result = await usersService.startProcessingRequest(arxivId);

    return NextResponse.json(result);
  } catch (error) {
    console.error('Error starting paper processing:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
