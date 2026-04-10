/**
 * Research Frontiers API Route
 *
 * Returns bump chart data for the /frontiers page: theme lines with
 * weekly ranks, velocity, status, and paper lists per week.
 *
 * Responsibilities:
 * - GET /api/frontiers - returns FrontiersData
 */

import { NextResponse } from 'next/server';
import * as frontiersService from '@/services/frontiers.service';
import type { FrontiersData } from '@/services/frontiers.service';

export const dynamic = 'force-dynamic';

// ============================================================================
// ENDPOINTS
// ============================================================================

interface ErrorResponse {
  error: string;
}

/**
 * GET /api/frontiers
 * @returns FrontiersData with themes and weeks for the bump chart
 */
export async function GET(): Promise<NextResponse<FrontiersData | ErrorResponse>> {
  try {
    const data = await frontiersService.getFrontiersData();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Error fetching frontiers data:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
