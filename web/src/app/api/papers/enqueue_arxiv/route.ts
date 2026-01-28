/**
 * Enqueue ArXiv Paper API Route
 *
 * Creates a paper record for arXiv processing.
 * - POST: Enqueue an arXiv paper for processing
 */

import { NextRequest, NextResponse } from 'next/server';
import * as papersService from '@/services/papers.service';
import type { EnqueueArxivRequest, EnqueueArxivResponse } from '@/types/paper';

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
 * POST handler for enqueuing an arXiv paper for processing.
 * @param request - The incoming Next.js request with JSON body containing url
 * @returns JSON response with job information
 */
export async function POST(request: NextRequest): Promise<NextResponse<EnqueueArxivResponse | ErrorResponse>> {
  try {
    const body = await request.json() as EnqueueArxivRequest;

    if (!body.url) {
      return NextResponse.json({ error: 'Missing required field: url' }, { status: 400 });
    }

    const result = await papersService.enqueueArxiv(body.url);
    return NextResponse.json(result);
  } catch (error) {
    // Check for JSON parse errors
    if (error instanceof SyntaxError) {
      return NextResponse.json({ error: 'Invalid JSON in request body' }, { status: 400 });
    }

    console.error('Error enqueuing arXiv paper:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
