/**
 * Unit tests for the Auth Service
 *
 * Tests the client-side authentication utilities using Supabase Auth.
 *
 * Responsibilities:
 * - Test magic link sign-in calls Supabase correctly
 * - Test sign-out calls Supabase correctly
 * - Test error handling when Supabase returns errors
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ============================================================================
// MOCKS
// ============================================================================

const mockSignInWithOtp = vi.fn();
const mockSignOut = vi.fn();
const mockGetUser = vi.fn();
const mockOnAuthStateChange = vi.fn();

vi.mock('@/lib/supabase/client', () => ({
  createClient: vi.fn(() => ({
    auth: {
      signInWithOtp: mockSignInWithOtp,
      signOut: mockSignOut,
      getUser: mockGetUser,
      onAuthStateChange: mockOnAuthStateChange,
    },
  })),
}));

// Import after mocking
import { signInWithMagicLink, signOut, getSupabaseClient } from './auth';

// ============================================================================
// TEST SETUP
// ============================================================================

beforeEach(() => {
  vi.clearAllMocks();

  // Setup default window.location for tests
  vi.stubGlobal('window', {
    location: {
      origin: 'http://localhost:3000',
    },
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ============================================================================
// getSupabaseClient TESTS
// ============================================================================

describe('getSupabaseClient', () => {
  it('returns a Supabase client instance', () => {
    const client = getSupabaseClient();

    expect(client).toBeDefined();
    expect(client.auth).toBeDefined();
  });
});

// ============================================================================
// signInWithMagicLink TESTS
// ============================================================================

describe('signInWithMagicLink', () => {
  it('calls signInWithOtp with correct email and default redirect URL', async () => {
    mockSignInWithOtp.mockResolvedValue({ error: null });

    const result = await signInWithMagicLink('test@example.com');

    expect(mockSignInWithOtp).toHaveBeenCalledTimes(1);
    expect(mockSignInWithOtp).toHaveBeenCalledWith({
      email: 'test@example.com',
      options: {
        emailRedirectTo: 'http://localhost:3000/auth/callback',
      },
    });
    expect(result).toEqual({ error: null });
  });

  it('calls signInWithOtp with custom redirect URL when provided', async () => {
    mockSignInWithOtp.mockResolvedValue({ error: null });

    const result = await signInWithMagicLink(
      'test@example.com',
      'https://example.com/custom-callback'
    );

    expect(mockSignInWithOtp).toHaveBeenCalledWith({
      email: 'test@example.com',
      options: {
        emailRedirectTo: 'https://example.com/custom-callback',
      },
    });
    expect(result).toEqual({ error: null });
  });

  it('returns error object when Supabase returns an error', async () => {
    const mockError = {
      name: 'AuthApiError',
      message: 'Email rate limit exceeded',
      status: 429,
    };
    mockSignInWithOtp.mockResolvedValue({ error: mockError });

    const result = await signInWithMagicLink('test@example.com');

    expect(result).toEqual({ error: mockError });
  });

  it('handles invalid email format (Supabase returns error)', async () => {
    const mockError = {
      name: 'AuthApiError',
      message: 'Invalid email format',
      status: 400,
    };
    mockSignInWithOtp.mockResolvedValue({ error: mockError });

    const result = await signInWithMagicLink('invalid-email');

    expect(mockSignInWithOtp).toHaveBeenCalledWith({
      email: 'invalid-email',
      options: {
        emailRedirectTo: 'http://localhost:3000/auth/callback',
      },
    });
    expect(result).toEqual({ error: mockError });
  });

  it('handles network errors from Supabase', async () => {
    const networkError = {
      name: 'AuthRetryableFetchError',
      message: 'Network request failed',
      status: 0,
    };
    mockSignInWithOtp.mockResolvedValue({ error: networkError });

    const result = await signInWithMagicLink('test@example.com');

    expect(result).toEqual({ error: networkError });
  });
});

// ============================================================================
// signOut TESTS
// ============================================================================

describe('signOut', () => {
  it('calls Supabase signOut and returns null error on success', async () => {
    mockSignOut.mockResolvedValue({ error: null });

    const result = await signOut();

    expect(mockSignOut).toHaveBeenCalledTimes(1);
    expect(result).toEqual({ error: null });
  });

  it('returns error object when Supabase signOut fails', async () => {
    const mockError = {
      name: 'AuthApiError',
      message: 'Session not found',
      status: 400,
    };
    mockSignOut.mockResolvedValue({ error: mockError });

    const result = await signOut();

    expect(result).toEqual({ error: mockError });
  });

  it('handles network errors during sign out', async () => {
    const networkError = {
      name: 'AuthRetryableFetchError',
      message: 'Network request failed',
      status: 0,
    };
    mockSignOut.mockResolvedValue({ error: networkError });

    const result = await signOut();

    expect(result).toEqual({ error: networkError });
  });
});
