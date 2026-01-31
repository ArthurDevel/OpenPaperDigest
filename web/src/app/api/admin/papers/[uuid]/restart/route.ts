/**
 * Admin Paper Restart API Route
 *
 * Allows administrators to restart paper processing.
 * - POST: Reset paper status to allow reprocessing
 * - Requires HTTP Basic authentication
 */

import { NextRequest, NextResponse } from 'next/server';
import { adminGuard } from '@/lib/admin-auth';
import * as papersService from '@/services/papers.service';

// ============================================================================
// TYPES
// ============================================================================

interface RestartSuccessResponse {
  paperUuid: string;
  status: string;
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
 * POST handler for restarting paper processing.
 * Resets the paper status to 'not_started' and clears error/timing fields.
 * @param request - The incoming Next.js request
 * @param context - Route context containing the paper UUID
 * @returns JSON response with updated paper status or error
 */
export async function POST(
  request: NextRequest,
  context: RouteParams
): Promise<NextResponse<RestartSuccessResponse | ErrorResponse>> {
  // Defense-in-depth: middleware handles auth, this is a fallback
  const authError = adminGuard(request);
  if (authError) return authError;

  try {
    const { uuid } = await context.params;

    // Validate UUID format
    if (!uuid || typeof uuid !== 'string') {
      return NextResponse.json({ error: 'Invalid paper UUID' }, { status: 400 });
    }

    const result = await papersService.restartPaper(uuid);

    return NextResponse.json({
      paperUuid: result.paperUuid,
      status: result.status,
    });
  } catch (error) {
    // Handle known errors
    if (error instanceof Error) {
      if (error.message.includes('not found')) {
        return NextResponse.json({ error: 'Paper not found' }, { status: 404 });
      }
      if (error.message.includes('already processing')) {
        return NextResponse.json({ error: 'Paper is already processing' }, { status: 409 });
      }
    }

    console.error('Error restarting paper:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
