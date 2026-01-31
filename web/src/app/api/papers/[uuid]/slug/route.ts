/**
 * Paper Slug API Route
 *
 * Manages slugs for a specific paper.
 * - GET: Get the current slug for a paper
 * - POST: Create a slug for a paper (idempotent)
 */

import { NextRequest, NextResponse } from 'next/server';
import * as slugsService from '@/services/slugs.service';
import type { ResolveSlugResponse } from '@/types/paper';

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
 * GET handler for fetching the slug for a paper.
 * @param request - The incoming Next.js request
 * @param params - Route params containing the paper UUID
 * @returns JSON response with slug information
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ uuid: string }> }
): Promise<NextResponse<ResolveSlugResponse | ErrorResponse>> {
  try {
    const { uuid } = await params;

    if (!uuid) {
      return NextResponse.json({ error: 'Missing UUID parameter' }, { status: 400 });
    }

    const result = await slugsService.getSlugForPaper(uuid);
    return NextResponse.json(result);
  } catch (error) {
    console.error('Error getting slug for paper:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}

/**
 * POST handler for creating a slug for a paper.
 * This is idempotent - returns existing slug if one already exists.
 * @param request - The incoming Next.js request
 * @param params - Route params containing the paper UUID
 * @returns JSON response with created or existing slug information
 */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ uuid: string }> }
): Promise<NextResponse<ResolveSlugResponse | ErrorResponse>> {
  try {
    const { uuid } = await params;

    if (!uuid) {
      return NextResponse.json({ error: 'Missing UUID parameter' }, { status: 400 });
    }

    const result = await slugsService.createSlug(uuid);
    return NextResponse.json(result);
  } catch (error) {
    // Check for specific error messages from service
    if (error instanceof Error && error.message.includes('not found')) {
      return NextResponse.json({ error: 'Paper not found' }, { status: 404 });
    }

    console.error('Error creating slug for paper:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
