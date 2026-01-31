/**
 * Admin Paper Delete API Route
 *
 * Allows administrators to delete a paper by UUID.
 * - DELETE: Remove a paper and its associated slugs from the database
 * - Requires HTTP Basic authentication
 */

import { NextRequest, NextResponse } from 'next/server';
import { adminGuard } from '@/lib/admin-auth';
import * as papersService from '@/services/papers.service';

// ============================================================================
// TYPES
// ============================================================================

interface DeleteSuccessResponse {
  deleted: string;
}

interface ErrorResponse {
  error: string;
}

interface RouteParams {
  params: Promise<{ uuid: string }>;
}

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * DELETE handler for removing a paper.
 * Deletes the paper record and associated slugs from the database.
 * @param request - The incoming Next.js request
 * @param context - Route context containing the paper UUID
 * @returns JSON response with deleted UUID or error
 */
export async function DELETE(
  request: NextRequest,
  context: RouteParams
): Promise<NextResponse<DeleteSuccessResponse | ErrorResponse>> {
  // Defense-in-depth: middleware handles auth, this is a fallback
  const authError = adminGuard(request);
  if (authError) return authError;

  try {
    const { uuid } = await context.params;

    // Validate UUID format
    if (!uuid || typeof uuid !== 'string') {
      return NextResponse.json({ error: 'Invalid paper UUID' }, { status: 400 });
    }

    const deleted = await papersService.deletePaper(uuid);

    if (!deleted) {
      return NextResponse.json({ error: 'Paper not found' }, { status: 404 });
    }

    return NextResponse.json({ deleted: uuid });
  } catch (error) {
    console.error('Error deleting paper:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
