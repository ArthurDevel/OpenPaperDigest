'use client';

/**
 * Login Page
 *
 * Provides magic link authentication for users.
 *
 * Responsibilities:
 * - Display sign-in form for unauthenticated users
 * - Send magic link emails via Supabase
 * - Display sign-out option for authenticated users
 */

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useSession, signInWithMagicLink, signOut } from '@/services/auth';

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export default function LoginPage() {
  const { user, isLoading } = useSession();
  const router = useRouter();

  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  // ==========================================================================
  // EVENT HANDLERS
  // ==========================================================================

  /**
   * Handles form submission to send magic link.
   * @param e - Form event
   */
  const handleSignIn = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    setLoading(true);
    setMessage('');
    setError('');

    const { error: signInError } = await signInWithMagicLink(email);

    setLoading(false);

    if (signInError) {
      setError(signInError.message ?? 'An error occurred');
    } else {
      setMessage('Magic link sent! Please check your email to sign in.');
      setEmail('');
    }
  };

  /**
   * Handles sign out button click.
   */
  const handleSignOut = async (): Promise<void> => {
    setLoading(true);
    await signOut();
    router.push('/');
    setLoading(false);
  };

  // ==========================================================================
  // RENDER
  // ==========================================================================

  if (isLoading) {
    return (
      <div className="container mx-auto max-w-md p-8 text-center">
        <p>Loading session...</p>
      </div>
    );
  }

  if (user) {
    return (
      <div className="container mx-auto max-w-md p-8 text-center">
        <h1 className="text-3xl font-bold mb-6">You are Logged In</h1>
        <p className="mb-6">Welcome! You are already authenticated.</p>
        <button
          onClick={handleSignOut}
          disabled={loading}
          className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:bg-red-300"
        >
          {loading ? 'Signing out...' : 'Sign Out'}
        </button>
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-md p-8">
      <h1 className="text-3xl font-bold mb-6 text-center">Sign In</h1>
      <p className="text-gray-600 dark:text-gray-300 mb-6 text-center">
        Enter your email to receive a magic link to sign in. No password required.
      </p>
      <form onSubmit={handleSignIn} className="space-y-6">
        <div>
          <label
            htmlFor="email"
            className="block text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            Email address
          </label>
          <div className="mt-1">
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              className="appearance-none block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={loading || !!message}
            />
          </div>
        </div>

        <div>
          <button
            type="submit"
            disabled={loading || !!message}
            className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:bg-indigo-300 disabled:cursor-not-allowed"
          >
            {loading ? 'Sending...' : 'Send Magic Link'}
          </button>
        </div>
      </form>
      {message && (
        <div className="mt-4 p-4 bg-green-100 dark:bg-green-900/30 border border-green-400 dark:border-green-700 text-green-700 dark:text-green-300 rounded">
          <p>{message}</p>
        </div>
      )}
      {error && (
        <div className="mt-4 p-4 bg-red-100 dark:bg-red-900/30 border border-red-400 dark:border-red-700 text-red-700 dark:text-red-300 rounded">
          <p>{error}</p>
        </div>
      )}
    </div>
  );
}
