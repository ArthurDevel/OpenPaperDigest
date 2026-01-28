/**
 * Health Check API Route
 *
 * Simple health check endpoint for deployment monitoring.
 * - Returns a simple status response to indicate the service is running
 * - Used by Railway and other deployment platforms for health checks
 * - Accessible at both /api/health and /health (via rewrite)
 */

import { NextResponse } from 'next/server';

// ============================================================================
// TYPES
// ============================================================================

interface HealthResponse {
  status: string;
}

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * Returns the health status of the application.
 * @returns JSON response with status "ok"
 */
export async function GET(): Promise<NextResponse<HealthResponse>> {
  return NextResponse.json({ status: 'ok' });
}
