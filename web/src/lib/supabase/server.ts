/**
 * Supabase Server Client
 *
 * Creates a Supabase client for use in Server Components and Route Handlers.
 * Uses cookies to maintain user sessions and anon key with RLS.
 */

import { createServerClient } from '@supabase/ssr';
import { cookies } from 'next/headers';
import type { Database } from '@/lib/types/database.types';

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
 * Reads cookies to access the authenticated user's session.
 * @returns Supabase client with user session from cookies
 */
export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient<Database>(SUPABASE_URL, SUPABASE_ANON_KEY, {
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
          // setAll can fail in Server Components (read-only context)
          // Session refresh will be handled by middleware instead
        }
      },
    },
  });
}
