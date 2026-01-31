/**
 * arXiv Metadata API Route
 *
 * Fetches metadata for an arXiv paper by its ID or URL.
 * - Accepts arXiv IDs (e.g., "2301.12345") or full URLs
 * - Normalizes the input and fetches metadata from arXiv API
 * - Returns structured metadata including title, authors, abstract, etc.
 */

import { NextRequest, NextResponse } from 'next/server';
import { normalizeId, fetchMetadata, type ArxivMetadata } from '@/lib/arxiv';

// ============================================================================
// TYPES
// ============================================================================

interface RouteParams {
  params: Promise<{ id: string }>;
}

interface ErrorResponse {
  error: string;
}

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * Fetches arXiv paper metadata by ID or URL.
 * @param request - The incoming request object
 * @param context - Route context containing the dynamic segment
 * @returns ArxivMetadata on success, error response on failure
 */
export async function GET(
  request: NextRequest,
  context: RouteParams
): Promise<NextResponse<ArxivMetadata | ErrorResponse>> {
  const { id } = await context.params;

  // The ID might be URL-encoded (e.g., slashes in old-style IDs)
  const decodedId = decodeURIComponent(id);

  // Normalize the input to extract a clean arXiv ID
  let arxivId: string;
  try {
    const normalized = normalizeId(decodedId);
    arxivId = normalized.arxivId;
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Invalid arXiv identifier';
    return NextResponse.json({ error: message }, { status: 400 });
  }

  // Fetch metadata from arXiv API
  try {
    const metadata = await fetchMetadata(arxivId);
    return NextResponse.json(metadata);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to fetch arXiv metadata';

    // Distinguish between "not found" and other errors
    if (message.includes('No metadata found')) {
      return NextResponse.json({ error: message }, { status: 404 });
    }

    return NextResponse.json({ error: message }, { status: 500 });
  }
}
