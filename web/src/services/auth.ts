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
// CONSTANTS
// ============================================================================

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || '';

// ============================================================================
// TYPES
// ============================================================================

export interface UseSessionReturn {
  user: User | null;
  isLoading: boolean;
}

type SessionListener = (state: UseSessionReturn) => void;

// ============================================================================
// SHARED SESSION STATE
// ============================================================================

let sessionState: UseSessionReturn = {
  user: null,
  isLoading: true,
};
let sessionInitPromise: Promise<void> | null = null;
let hasSessionSubscription = false;
const sessionListeners = new Set<SessionListener>();

function emitSessionState(): void {
  sessionListeners.forEach((listener) => {
    listener(sessionState);
  });
}

function updateSessionState(user: User | null, isLoading: boolean): void {
  sessionState = { user, isLoading };
  emitSessionState();
}

function subscribeToSessionChanges(supabase: SupabaseClient): void {
  if (hasSessionSubscription) {
    return;
  }

  hasSessionSubscription = true;

  supabase.auth.onAuthStateChange((_event, session) => {
    updateSessionState(session?.user ?? null, false);
  });
}

async function ensureSessionLoaded(): Promise<void> {
  const supabase = createClient();

  subscribeToSessionChanges(supabase);

  if (!sessionState.isLoading) {
    return;
  }

  if (sessionInitPromise) {
    await sessionInitPromise;
    return;
  }

  sessionInitPromise = supabase.auth
    .getUser()
    .then(({ data: { user } }) => {
      updateSessionState(user, false);
    })
    .catch(() => {
      updateSessionState(null, false);
    })
    .finally(() => {
      sessionInitPromise = null;
    });

  await sessionInitPromise;
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
  const [state, setState] = useState<UseSessionReturn>(sessionState);

  useEffect(() => {
    sessionListeners.add(setState);
    void ensureSessionLoaded();

    return () => {
      sessionListeners.delete(setState);
    };
  }, []);

  return state;
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
      emailRedirectTo: emailRedirectTo || `${SITE_URL}/auth/callback`,
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
