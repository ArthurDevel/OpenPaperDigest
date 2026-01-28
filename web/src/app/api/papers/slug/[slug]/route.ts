/**
 * Resolve Paper Slug API Route
 *
 * Resolves a slug to its associated paper UUID.
 * - GET: Resolve a slug to get paper UUID
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
 * GET handler for resolving a paper slug.
 * @param request - The incoming Next.js request
 * @param params - Route params containing the slug
 * @returns JSON response with paper UUID, slug, and tombstone status
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string }> }
): Promise<NextResponse<ResolveSlugResponse | ErrorResponse>> {
  try {
    const { slug } = await params;

    if (!slug) {
      return NextResponse.json({ error: 'Missing slug parameter' }, { status: 400 });
    }

    const result = await slugsService.resolveSlug(slug);
    return NextResponse.json(result);
  } catch (error) {
    console.error('Error resolving slug:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
