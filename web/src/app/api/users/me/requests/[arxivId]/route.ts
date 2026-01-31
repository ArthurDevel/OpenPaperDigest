/**
 * User Request Item API Route
 *
 * Manages individual paper processing requests for the authenticated user.
 * - GET: Check if a request exists for an arXiv paper
 * - POST: Add a request for an arXiv paper (requires title, authors in body)
 * - DELETE: Remove a request for an arXiv paper
 */

import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import * as usersService from '@/services/users.service';
import type { ExistsResponse, CreatedResponse, DeletedResponse } from '@/types/user';

// ============================================================================
// TYPES
// ============================================================================

interface ErrorResponse {
  error: string;
}

interface AddRequestBody {
  title?: string | null;
  authors?: string | null;
}

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * GET handler to check if a request exists for an arXiv paper.
 * Requires authentication.
 * @param request - The incoming Next.js request
 * @param params - Route params containing the arXiv ID
 * @returns JSON response indicating whether request exists
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ arxivId: string }> }
): Promise<NextResponse<ExistsResponse | ErrorResponse>> {
  try {
    // Verify authentication
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { arxivId } = await params;
    if (!arxivId) {
      return NextResponse.json({ error: 'Missing arXiv ID parameter' }, { status: 400 });
    }

    const userId = session.user.id;
    const result = await usersService.doesRequestExist(userId, arxivId);
    return NextResponse.json(result);
  } catch (error) {
    console.error('Error checking request:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}

/**
 * POST handler to add a paper request.
 * Requires authentication and title/authors in request body.
 * @param request - The incoming Next.js request with title and authors in body
 * @param params - Route params containing the arXiv ID
 * @returns JSON response indicating whether request was created
 */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ arxivId: string }> }
): Promise<NextResponse<CreatedResponse | ErrorResponse>> {
  try {
    // Verify authentication
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { arxivId } = await params;
    if (!arxivId) {
      return NextResponse.json({ error: 'Missing arXiv ID parameter' }, { status: 400 });
    }

    // Parse request body for title and authors
    const body = (await request.json()) as AddRequestBody;
    const title = body.title ?? null;
    const authors = body.authors ?? null;

    const userId = session.user.id;
    const result = await usersService.addRequest(userId, arxivId, title, authors);
    return NextResponse.json(result);
  } catch (error) {
    // Check for specific error messages from service
    if (error instanceof Error && error.message.includes('User not found')) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    console.error('Error adding request:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}

/**
 * DELETE handler to remove a paper request.
 * Requires authentication.
 * @param request - The incoming Next.js request
 * @param params - Route params containing the arXiv ID
 * @returns JSON response indicating whether request was removed
 */
export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ arxivId: string }> }
): Promise<NextResponse<DeletedResponse | ErrorResponse>> {
  try {
    // Verify authentication
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { arxivId } = await params;
    if (!arxivId) {
      return NextResponse.json({ error: 'Missing arXiv ID parameter' }, { status: 400 });
    }

    const userId = session.user.id;
    const result = await usersService.removeRequest(userId, arxivId);
    return NextResponse.json(result);
  } catch (error) {
    console.error('Error removing request:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
