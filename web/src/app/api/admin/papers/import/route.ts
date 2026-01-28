/**
 * Admin Paper Import API Route
 *
 * Allows administrators to import paper JSON data directly.
 * - POST: Import a full paper JSON object, writes to data/paperjsons/ and upserts DB record
 * - Requires HTTP Basic authentication
 */

import { NextRequest, NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/admin-auth';
import * as papersService from '@/services/papers.service';

// ============================================================================
// TYPES
// ============================================================================

interface ImportSuccessResponse {
  success: true;
  uuid: string;
}

interface ErrorResponse {
  error: string;
}

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * POST handler for importing paper JSON.
 * Requires admin authentication via HTTP Basic auth.
 * @param request - The incoming Next.js request containing paper JSON in body
 * @returns JSON response with success status and paper UUID
 */
export async function POST(
  request: NextRequest
): Promise<NextResponse<ImportSuccessResponse | ErrorResponse>> {
  // Verify admin authentication
  try {
    await requireAdmin(request);
  } catch (response) {
    return response as NextResponse<ErrorResponse>;
  }

  try {
    // Parse request body
    const body = await request.json();

    // Validate that body is an object
    if (!body || typeof body !== 'object' || Array.isArray(body)) {
      return NextResponse.json(
        { error: 'Request body must be a JSON object' },
        { status: 400 }
      );
    }

    // Import the paper JSON (service handles validation and file writing)
    const result = await papersService.importPaperJson(body as Record<string, unknown>);

    return NextResponse.json({
      success: true,
      uuid: result.paperUuid,
    });
  } catch (error) {
    // Check for validation errors from the service
    if (error instanceof Error && error.message.includes('required')) {
      return NextResponse.json({ error: error.message }, { status: 400 });
    }

    console.error('Error importing paper JSON:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
