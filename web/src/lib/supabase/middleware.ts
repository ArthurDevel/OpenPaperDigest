/**
 * Supabase Middleware Client
 *
 * Creates a Supabase client for use in Next.js middleware.
 *
 * Responsibilities:
 * - Provide a Supabase client that can read/write cookies in middleware context
 * - Handle session refresh by returning modified response with updated cookies
 */

import { createServerClient } from '@supabase/ssr';
import { NextRequest, NextResponse } from 'next/server';
import type { SupabaseClient } from '@supabase/supabase-js';

// ============================================================================
// CONSTANTS
// ============================================================================

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

// ============================================================================
// TYPES
// ============================================================================

interface MiddlewareClientResult {
  supabase: SupabaseClient;
  response: NextResponse;
}

// ============================================================================
// MAIN EXPORT
// ============================================================================

/**
 * Creates a Supabase client for middleware usage.
 * @param request - The incoming Next.js request
 * @returns Object containing the Supabase client and the response to return
 */
export function createClient(request: NextRequest): MiddlewareClientResult {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        // Update cookies on the request for downstream handlers
        cookiesToSet.forEach(({ name, value }) => {
          request.cookies.set(name, value);
        });
        // Create new response with updated request
        response = NextResponse.next({ request });
        // Also set cookies on the response for the browser
        cookiesToSet.forEach(({ name, value, options }) => {
          response.cookies.set(name, value, options);
        });
      },
    },
  });

  return { supabase, response };
}
