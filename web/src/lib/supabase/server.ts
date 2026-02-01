/**
 * Supabase Server Client
 *
 * Creates a Supabase client for use in Server Components and Route Handlers.
 * Uses the service role key to bypass RLS for server-side operations.
 */

import { createClient as createSupabaseClient } from '@supabase/supabase-js';
import type { Database } from '@/lib/types/database.types';

// ============================================================================
// CONSTANTS
// ============================================================================

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY!;

// ============================================================================
// MAIN EXPORT
// ============================================================================

/**
 * Creates a Supabase client for server-side usage (Server Components, Route Handlers).
 * Uses service role key to bypass RLS - no cookie/session management needed.
 */
export async function createClient() {
  return createSupabaseClient<Database>(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
}
