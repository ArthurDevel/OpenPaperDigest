import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

/**
 * GET handler for paper data
 * Fetches paper data from backend API instead of file system
 * 
 * @param request - Request object with optional 'file' query parameter
 * @returns List of available papers or specific paper data
 */
export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const requestedFile = url.searchParams.get('file');

    if (!requestedFile) {
      // Return list of available papers from backend API
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(`${apiUrl}/admin/papers?status=completed`, {
        headers: {
          'Authorization': `Basic ${Buffer.from(`admin:${process.env.ADMIN_BASIC_PASSWORD || ''}`).toString('base64')}`
        }
      });
      
      if (!response.ok) {
        throw new Error(`Failed to fetch papers list: ${response.status}`);
      }
      
      const papers = await response.json();
      const files = papers.map((p: any) => `${p.paper_uuid}.json`);
      return NextResponse.json({ files }, { status: 200 });
    }

    // Extract UUID from filename
    const uuid = requestedFile.replace('.json', '');

    // Fetch paper summary from backend API (lightweight endpoint)
    // Use /summary instead of /papers/{uuid} to avoid downloading 17MB of page images
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const response = await fetch(`${apiUrl}/papers/${uuid}/summary`);

    if (!response.ok) {
      throw new Error(`Paper not found: ${response.status}`);
    }

    const data = await response.json();
    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: `Failed to fetch paper: ${message}` }, { status: 500 });
  }
}


