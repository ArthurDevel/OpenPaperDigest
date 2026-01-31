/**
 * Authentication Service
 *
 * Provides client-side authentication utilities using Supabase Auth.
 *
 * Responsibilities:
 * - Expose Supabase browser client for auth operations
 * - Provide React hook for session state management
 * - Handle magic link sign-in and sign-out
 */

import { useState, useEffect } from 'react';
import { createClient } from '@/lib/supabase/client';
import type { User, AuthError, SupabaseClient } from '@supabase/supabase-js';

// ============================================================================
// TYPES
// ============================================================================

export interface UseSessionReturn {
  user: User | null;
  isLoading: boolean;
}

// ============================================================================
// CLIENT ACCESS
// ============================================================================

/**
 * Returns the Supabase browser client for direct usage.
 * @returns The Supabase client instance
 */
export function getSupabaseClient(): SupabaseClient {
  return createClient();
}

// ============================================================================
// HOOKS
// ============================================================================

/**
 * React hook that subscribes to auth state changes and returns the current user.
 * @returns Object containing user (or null) and loading state
 */
export function useSession(): UseSessionReturn {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const supabase = createClient();

    // Get initial session
    supabase.auth.getUser().then(({ data: { user } }) => {
      setUser(user);
      setIsLoading(false);
    });

    // Subscribe to auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
      setIsLoading(false);
    });

    return () => {
      subscription.unsubscribe();
    };
  }, []);

  return { user, isLoading };
}

// ============================================================================
// AUTH ACTIONS
// ============================================================================

/**
 * Sends a magic link email to the specified address.
 * @param email - The email address to send the magic link to
 * @param emailRedirectTo - Optional URL to redirect to after confirmation (defaults to /auth/callback)
 * @returns Object containing any error that occurred
 */
export async function signInWithMagicLink(
  email: string,
  emailRedirectTo?: string
): Promise<{ error: AuthError | null }> {
  const supabase = createClient();
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: {
      emailRedirectTo: emailRedirectTo || `${window.location.origin}/auth/callback`,
    },
  });
  return { error };
}

/**
 * Signs out the current user.
 * @returns Object containing any error that occurred
 */
export async function signOut(): Promise<{ error: AuthError | null }> {
  const supabase = createClient();
  const { error } = await supabase.auth.signOut();
  return { error };
}
