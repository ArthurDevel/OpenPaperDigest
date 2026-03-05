/**
 * Supabase Browser Client
 *
 * Creates a Supabase client for use in browser/client-side code.
 * Uses singleton pattern to reuse the same client instance.
 *
 * Responsibilities:
 * - Provide a browser-safe Supabase client for React components
 * - Handle cookie-based session management automatically
 * - Auto-sign-in anonymously on first visit (no existing session)
 */

import { createBrowserClient } from '@supabase/ssr';
import type { SupabaseClient } from '@supabase/supabase-js';

// ============================================================================
// CONSTANTS
// ============================================================================

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

// ============================================================================
// SINGLETON
// ============================================================================

let client: SupabaseClient | null = null;
let authPromise: Promise<void> | null = null;

// ============================================================================
// MAIN EXPORTS
// ============================================================================

/**
 * Creates or returns the singleton Supabase browser client.
 * @returns The Supabase client for browser-side usage
 */
export function createClient(): SupabaseClient {
  if (client) {
    return client;
  }

  client = createBrowserClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  return client;
}

/**
 * Ensures the user has an authenticated Supabase session.
 * If no session exists, signs in anonymously to get a user ID and JWT.
 * Anonymous users get full RLS access and can be promoted to permanent users later.
 * Safe to call multiple times -- deduplicates concurrent calls.
 * @returns The Supabase client with an active session
 */
export async function ensureAuthenticated(): Promise<SupabaseClient> {
  const supabase = createClient();

  // Deduplicate concurrent calls
  if (authPromise) {
    await authPromise;
    return supabase;
  }

  authPromise = (async () => {
    const { data: { session } } = await supabase.auth.getSession();

    if (!session) {
      const { error } = await supabase.auth.signInAnonymously();
      if (error) {
        throw new Error(`Anonymous sign-in failed: ${error.message}`);
      }
    }
  })();

  try {
    await authPromise;
  } finally {
    authPromise = null;
  }

  return supabase;
}
