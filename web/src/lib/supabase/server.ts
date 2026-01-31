/**
 * Supabase Server Client
 *
 * Creates a Supabase client for use in Server Components and Route Handlers.
 *
 * Responsibilities:
 * - Provide a server-safe Supabase client that can read/write cookies
 * - Handle cookie-based session management for server-side auth
 */

import { createServerClient } from '@supabase/ssr';
import { cookies } from 'next/headers';
import type { SupabaseClient } from '@supabase/supabase-js';

// ============================================================================
// CONSTANTS
// ============================================================================

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

// ============================================================================
// MAIN EXPORT
// ============================================================================

/**
 * Creates a Supabase client for server-side usage (Server Components, Route Handlers).
 * @returns Promise resolving to a Supabase client configured with cookie access
 */
export async function createClient(): Promise<SupabaseClient> {
  const cookieStore = await cookies();

  return createServerClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) => {
            cookieStore.set(name, value, options);
          });
        } catch {
          // setAll is called from a Server Component where cookies cannot be set.
          // This is expected behavior when refreshing sessions in RSC.
        }
      },
    },
  });
}
