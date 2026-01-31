/**
 * Admin Requested Paper Delete API Route
 *
 * Allows administrators to delete paper requests by arXiv ID.
 * - DELETE: Remove all user requests for a specific arXiv ID
 * - Requires HTTP Basic authentication
 *
 * Note: The [id] parameter is the arXiv ID (or URL), not a numeric ID.
 * This matches the Python admin endpoint behavior.
 */

import { NextRequest, NextResponse } from 'next/server';
import { adminGuard } from '@/lib/admin-auth';
import { normalizeId } from '@/lib/arxiv';
import * as usersService from '@/services/users.service';
import type { DeleteRequestedResponse } from '@/types/user';

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
 * DELETE handler for removing all paper requests for an arXiv ID.
 * Accepts arXiv ID or URL and normalizes it before deletion.
 * @param request - The incoming Next.js request
 * @param context - Route context containing the arXiv ID or URL
 * @returns JSON response with deleted arXiv ID or error
 */
export async function DELETE(
  request: NextRequest,
  context: RouteParams
): Promise<NextResponse<DeleteRequestedResponse | ErrorResponse>> {
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

    // Delete all requests for this arXiv ID
    await usersService.deleteAllRequestsForArxiv(arxivId);

    return NextResponse.json({ deleted: arxivId });
  } catch (error) {
    console.error('Error deleting paper requests:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
