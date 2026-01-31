/**
 * User Requests API Route
 *
 * Manages the authenticated user's paper processing requests.
 * - GET: Retrieve all paper requests made by the user
 */

import { NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase/server';
import * as usersService from '@/services/users.service';
import type { UserRequestItem } from '@/types/user';

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
 * GET handler for fetching user's paper requests.
 * Requires authentication.
 * @returns JSON response with array of user's paper requests
 */
export async function GET(): Promise<NextResponse<UserRequestItem[] | ErrorResponse>> {
  try {
    // Verify authentication
    const supabase = await createClient();
    const { data: { user }, error } = await supabase.auth.getUser();
    if (error || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const userId = user.id;
    const requests = await usersService.listRequests(userId);
    return NextResponse.json(requests);
  } catch (error) {
    console.error('Error fetching user requests:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
