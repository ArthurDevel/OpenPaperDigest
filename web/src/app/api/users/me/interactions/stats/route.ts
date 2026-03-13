/**
 * User Interaction Stats API Route
 *
 * Returns aggregated interaction statistics and reading history for the
 * authenticated user.
 *
 * Responsibilities:
 * - GET: Authenticate user and return interaction stats (counts, reading time, history)
 */

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase/server';
import * as interactionsService from '@/services/interactions.service';
import type { InteractionStats } from '@/types/recommendation';

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
 * GET handler for user interaction stats.
 * Requires authentication (anonymous or permanent user).
 * @param _request - The incoming request (unused)
 * @returns InteractionStats on success, 401 if unauthenticated, 500 on error
 */
export async function GET(
  _request: NextRequest
): Promise<NextResponse<InteractionStats | ErrorResponse>> {
  try {
    // Verify authentication
    const supabase = await createClient();
    const { data: { user }, error: authError } = await supabase.auth.getUser();
    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const stats = await interactionsService.getInteractionStats(user.id);

    return NextResponse.json(stats);
  } catch (error) {
    console.error('Error fetching interaction stats:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
