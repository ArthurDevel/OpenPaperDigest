/**
 * Next.js Middleware
 *
 * Handles two authentication concerns:
 * 1. Supabase session refresh - runs on ALL routes to keep sessions alive
 * 2. Basic Auth protection - protects admin routes (/management, /api/admin/*)
 */

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase/middleware';

// ============================================================================
// CONSTANTS
// ============================================================================

const BASIC_REALM = 'Management';
const ADMIN_USER = 'admin';
const ADMIN_PASS = process.env.ADMIN_BASIC_PASSWORD || '';

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

function unauthorized(): NextResponse {
  return new NextResponse('Unauthorized', {
    status: 401,
    headers: { 'WWW-Authenticate': `Basic realm="${BASIC_REALM}", charset="UTF-8"` },
  });
}

function needsAdmin(url: URL, method: string): boolean {
  const p = url.pathname;
  if (p === '/management') return true;
  if (p === '/layouttests/data' && (method === 'POST' || method === 'DELETE')) return true;
  if (p.startsWith('/api/admin/')) return true;
  return false;
}

function toBase64(s: string): string {
  try {
    if (typeof Buffer !== 'undefined') return Buffer.from(s, 'utf-8').toString('base64');
  } catch {}
  try {
    if (typeof btoa !== 'undefined') return btoa(s);
  } catch {}
  return s;
}

// ============================================================================
// MAIN MIDDLEWARE
// ============================================================================

export async function middleware(request: NextRequest): Promise<NextResponse> {
  // 1. SUPABASE SESSION REFRESH (runs on ALL routes)
  const { supabase, response } = createClient(request);
  await supabase.auth.getUser();

  // 2. BASIC AUTH FOR ADMIN ROUTES
  if (ADMIN_PASS) {
    const url = new URL(request.url);
    if (needsAdmin(url, request.method)) {
      const header = request.headers.get('authorization') || '';
      const expected = `Basic ${toBase64(`${ADMIN_USER}:${ADMIN_PASS}`)}`;
      if (header !== expected) return unauthorized();
    }
  }

  return response;
}

// ============================================================================
// CONFIG
// ============================================================================

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)'],
};
