/**
 * User List API Route
 *
 * Manages the authenticated user's paper list.
 * - GET: Retrieve all papers in user's saved list
 */

import { NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase/server';
import * as usersService from '@/services/users.service';
import type { UserListItem } from '@/types/user';

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
 * GET handler for fetching user's paper list.
 * Requires authentication.
 * @returns JSON response with array of papers in user's list
 */
export async function GET(): Promise<NextResponse<UserListItem[] | ErrorResponse>> {
  try {
    // Verify authentication
    const supabase = await createClient();
    const { data: { user }, error } = await supabase.auth.getUser();
    if (error || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const userId = user.id;
    const list = await usersService.getList(userId);
    return NextResponse.json(list);
  } catch (error) {
    console.error('Error fetching user list:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
