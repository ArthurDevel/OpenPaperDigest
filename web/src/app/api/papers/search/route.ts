/**
 * Search API Route
 *
 * Accepts a text query and returns semantically similar papers
 * using OpenRouter embeddings + pgvector similarity search.
 */

import { NextRequest, NextResponse } from 'next/server';
import { searchPapers } from '@/services/search.service';
import type { MinimalPaper } from '@/types/paper';

interface SearchResponse {
  items: MinimalPaper[];
}

interface ErrorResponse {
  error: string;
}

export async function POST(
  request: NextRequest
): Promise<NextResponse<SearchResponse | ErrorResponse>> {
  try {
    const body = await request.json();
    const query = body.query;

    if (!query || typeof query !== 'string' || query.trim().length === 0) {
      return NextResponse.json(
        { error: 'query is required' },
        { status: 400 }
      );
    }

    const items = await searchPapers(query.trim());

    return NextResponse.json({ items });
  } catch (error) {
    console.error('Error in search:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
