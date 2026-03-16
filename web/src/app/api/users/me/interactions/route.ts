/**
 * User Interactions API Route
 *
 * Receives batched interaction events from the client and persists them.
 * After responding, triggers an async preference cluster update via Next.js after().
 *
 * Responsibilities:
 * - POST: Validate user session and save interaction events
 * - Trigger async preference cluster update after response is sent
 */

import { after } from 'next/server';
import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase/server';
import * as interactionsService from '@/services/interactions.service';
import type { InteractionEvent } from '@/types/recommendation';

// ============================================================================
// TYPES
// ============================================================================

interface ErrorResponse {
  error: string;
}

interface InteractionsRequestBody {
  events: InteractionEvent[];
}

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * POST handler for saving user interaction events.
 * Requires authentication (anonymous or permanent user).
 * @param request - The incoming request with { events: InteractionEvent[] } body
 * @returns 200 on success, 401 if unauthenticated, 400 if invalid body
 */
export async function POST(
  request: NextRequest
): Promise<NextResponse<{ ok: true } | ErrorResponse>> {
  try {
    // Verify authentication
    const supabase = await createClient();
    const { data: { user }, error: authError } = await supabase.auth.getUser();
    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    // Parse and validate request body
    const body = await request.json() as InteractionsRequestBody;
    if (!body.events || !Array.isArray(body.events)) {
      return NextResponse.json({ error: 'Missing or invalid events array' }, { status: 400 });
    }

    if (body.events.length === 0) {
      return NextResponse.json({ ok: true as const });
    }

    await interactionsService.saveInteractions(user.id, body.events);

    // Extract unique paper UUIDs from expanded/read/saved events for cluster update
    // Seen events should not influence preference clusters
    const clusterPaperUuids = [...new Set(
      body.events
        .filter((e) => e.interactionType === 'expanded' || e.interactionType === 'read' || e.interactionType === 'saved')
        .map((e) => e.paperUuid)
    )];

    // Trigger async cluster update after response is sent (only if there are relevant events)
    if (clusterPaperUuids.length > 0) {
      after(async () => {
        try {
          await interactionsService.updatePreferenceClusters(user.id, clusterPaperUuids);
        } catch (err) {
          console.error('Error updating preference clusters:', err);
        }
      });
    }

    return NextResponse.json({ ok: true as const });
  } catch (error) {
    console.error('Error saving interactions:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
