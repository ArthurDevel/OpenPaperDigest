/**
 * Supabase Browser Client
 *
 * Creates a Supabase client for use in browser/client-side code.
 * Uses singleton pattern to reuse the same client instance.
 *
 * Responsibilities:
 * - Provide a browser-safe Supabase client for React components
 * - Handle cookie-based session management automatically
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

// ============================================================================
// MAIN EXPORT
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
