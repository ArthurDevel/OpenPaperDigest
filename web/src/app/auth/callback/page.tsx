'use client';

/**
 * Auth Callback Page
 *
 * Handles post-authentication redirect and executes queued actions.
 *
 * Responsibilities:
 * - Display authentication status to users
 * - Execute post-login actions stored in cookies
 * - Redirect users to appropriate destination after auth
 */

import { useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useSession } from '@/services/auth';
import { readAndClearPostLoginCookie } from '@/lib/postLogin';

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export default function AuthCallbackPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { user } = useSession();
  const [message] = useState('Authentication successful! Redirecting...');
  const [error, setError] = useState('');

  // ==========================================================================
  // EFFECTS
  // ==========================================================================

  useEffect(() => {
    const run = async (): Promise<void> => {
      // Check for error in URL params
      const errorParam = searchParams.get('error');
      if (errorParam) {
        setError(`Authentication failed: ${errorParam}. Please try signing in again.`);
        return;
      }

      // Wait for session to be available
      if (!user?.id) return;

      // Check for post-login cookie
      let redirectTo = '/';
      const payload = readAndClearPostLoginCookie();
      if (payload) {
        redirectTo = payload.redirect || '/';
        if (payload.url && payload.method) {
          try {
            const headers = new Headers();
            if (payload.body) headers.set('Content-Type', 'application/json');
            const resp = await fetch(payload.url, {
              method: payload.method,
              headers,
              credentials: 'include',
              body: payload.body ? JSON.stringify(payload.body) : undefined,
            });
            if (!resp.ok) {
              const txt = await resp.text();
              console.warn('Post-login action failed', resp.status, txt);
            }
          } catch (e) {
            console.warn('Post-login action error', e);
          }
        }
      }

      // Redirect to destination
      router.replace(redirectTo);
    };
    run();
  }, [searchParams, router, user]);

  // ==========================================================================
  // RENDER
  // ==========================================================================

  return (
    <div className="container mx-auto max-w-md p-8 text-center">
      <h1 className="text-2xl font-bold mb-4">Authentication</h1>
      {error ? (
        <div className="p-4 bg-red-100 border border-red-400 text-red-700 rounded">
          <p>{error}</p>
        </div>
      ) : (
        <div className="p-4 bg-blue-100 border border-blue-400 text-blue-700 rounded">
          <p>{message}</p>
        </div>
      )}
    </div>
  );
}
