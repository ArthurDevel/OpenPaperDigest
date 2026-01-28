/**
 * User Sync API Route
 *
 * Syncs user data from BetterAuth authentication hooks.
 * - POST: Create or update user record when user signs up or logs in
 */

import { NextRequest, NextResponse } from 'next/server';
import * as usersService from '@/services/users.service';
import type { SyncUserPayload } from '@/types/user';

// ============================================================================
// TYPES
// ============================================================================

interface ErrorResponse {
  error: string;
}

interface SyncResponse {
  created: boolean;
}

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * POST handler for syncing user data from BetterAuth.
 * Called by BetterAuth hook when a user is created.
 * @param request - The incoming Next.js request with user data in body
 * @returns JSON response indicating whether user was created
 */
export async function POST(
  request: NextRequest
): Promise<NextResponse<SyncResponse | ErrorResponse>> {
  try {
    const body = (await request.json()) as Partial<SyncUserPayload>;

    // Validate required fields
    if (!body.id || typeof body.id !== 'string') {
      return NextResponse.json({ error: 'Missing or invalid id field' }, { status: 400 });
    }

    if (!body.email || typeof body.email !== 'string') {
      return NextResponse.json({ error: 'Missing or invalid email field' }, { status: 400 });
    }

    const payload: SyncUserPayload = {
      id: body.id,
      email: body.email,
    };

    const result = await usersService.syncNewUser(payload);
    return NextResponse.json(result);
  } catch (error) {
    console.error('Error syncing user:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
