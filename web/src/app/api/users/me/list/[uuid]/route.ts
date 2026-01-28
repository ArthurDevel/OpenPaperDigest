/**
 * User List Item API Route
 *
 * Manages individual papers in the authenticated user's saved list.
 * - GET: Check if a paper is in the user's list
 * - POST: Add a paper to the user's list
 * - DELETE: Remove a paper from the user's list
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

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * GET handler to check if a paper is in user's list.
 * Requires authentication.
 * @param request - The incoming Next.js request
 * @param params - Route params containing the paper UUID
 * @returns JSON response indicating whether paper exists in list
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ uuid: string }> }
): Promise<NextResponse<ExistsResponse | ErrorResponse>> {
  try {
    // Verify authentication
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { uuid } = await params;
    if (!uuid) {
      return NextResponse.json({ error: 'Missing UUID parameter' }, { status: 400 });
    }

    const userId = session.user.id;
    const result = await usersService.isInList(userId, uuid);
    return NextResponse.json(result);
  } catch (error) {
    console.error('Error checking list item:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}

/**
 * POST handler to add a paper to user's list.
 * Requires authentication.
 * @param request - The incoming Next.js request
 * @param params - Route params containing the paper UUID
 * @returns JSON response indicating whether paper was added
 */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ uuid: string }> }
): Promise<NextResponse<CreatedResponse | ErrorResponse>> {
  try {
    // Verify authentication
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { uuid } = await params;
    if (!uuid) {
      return NextResponse.json({ error: 'Missing UUID parameter' }, { status: 400 });
    }

    const userId = session.user.id;
    const result = await usersService.addToList(userId, uuid);
    return NextResponse.json(result);
  } catch (error) {
    // Check for specific error messages from service
    if (error instanceof Error) {
      if (error.message.includes('User not found')) {
        return NextResponse.json({ error: 'User not found' }, { status: 404 });
      }
      if (error.message.includes('Paper not found')) {
        return NextResponse.json({ error: 'Paper not found' }, { status: 404 });
      }
    }

    console.error('Error adding to list:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}

/**
 * DELETE handler to remove a paper from user's list.
 * Requires authentication.
 * @param request - The incoming Next.js request
 * @param params - Route params containing the paper UUID
 * @returns JSON response indicating whether paper was removed
 */
export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ uuid: string }> }
): Promise<NextResponse<DeletedResponse | ErrorResponse>> {
  try {
    // Verify authentication
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { uuid } = await params;
    if (!uuid) {
      return NextResponse.json({ error: 'Missing UUID parameter' }, { status: 400 });
    }

    const userId = session.user.id;
    const result = await usersService.removeFromList(userId, uuid);
    return NextResponse.json(result);
  } catch (error) {
    console.error('Error removing from list:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
