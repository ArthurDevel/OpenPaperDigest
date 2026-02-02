/**
 * Unit tests for the Auth Service
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// ============================================================================
// MOCKS
// ============================================================================

const mockSignInWithOtp = vi.fn();
const mockSignOut = vi.fn();

vi.mock('@/lib/supabase/client', () => ({
  createClient: vi.fn(() => ({
    auth: {
      signInWithOtp: mockSignInWithOtp,
      signOut: mockSignOut,
      getUser: vi.fn(),
      onAuthStateChange: vi.fn(),
    },
  })),
}));

import { signInWithMagicLink, signOut, getSupabaseClient } from './auth';

// ============================================================================
// TESTS
// ============================================================================

beforeEach(() => {
  vi.clearAllMocks();
});

describe('getSupabaseClient', () => {
  it('returns a Supabase client', () => {
    const client = getSupabaseClient();
    expect(client).toBeDefined();
    expect(client.auth).toBeDefined();
  });
});

describe('signInWithMagicLink', () => {
  it('returns success when Supabase succeeds', async () => {
    mockSignInWithOtp.mockResolvedValue({ error: null });

    const result = await signInWithMagicLink('test@example.com');

    expect(mockSignInWithOtp).toHaveBeenCalledTimes(1);
    expect(result.error).toBeNull();
  });

  it('returns error when Supabase fails', async () => {
    const mockError = { message: 'Rate limit exceeded', status: 429 };
    mockSignInWithOtp.mockResolvedValue({ error: mockError });

    const result = await signInWithMagicLink('test@example.com');

    expect(result.error).toEqual(mockError);
  });

  it('uses custom redirect URL when provided', async () => {
    mockSignInWithOtp.mockResolvedValue({ error: null });

    await signInWithMagicLink('test@example.com', 'https://example.com/callback');

    expect(mockSignInWithOtp).toHaveBeenCalledWith({
      email: 'test@example.com',
      options: { emailRedirectTo: 'https://example.com/callback' },
    });
  });
});

describe('signOut', () => {
  it('returns success when Supabase succeeds', async () => {
    mockSignOut.mockResolvedValue({ error: null });

    const result = await signOut();

    expect(mockSignOut).toHaveBeenCalledTimes(1);
    expect(result.error).toBeNull();
  });

  it('returns error when Supabase fails', async () => {
    const mockError = { message: 'Session not found', status: 400 };
    mockSignOut.mockResolvedValue({ error: mockError });

    const result = await signOut();

    expect(result.error).toEqual(mockError);
  });
});
