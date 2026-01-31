/**
 * Magic Link Confirmation Route
 *
 * Handles magic link verification from Supabase email templates.
 *
 * Responsibilities:
 * - Extract token_hash and type from URL query parameters
 * - Verify the OTP token with Supabase
 * - Redirect to callback page on success or error page on failure
 */

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase/server';
import type { EmailOtpType } from '@supabase/supabase-js';

// ============================================================================
// MAIN HANDLER
// ============================================================================

/**
 * Handles GET requests for magic link verification.
 * @param request - The incoming request with token_hash and type query params
 * @returns Redirect response to callback or error page
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const { searchParams } = new URL(request.url);
  const token_hash = searchParams.get('token_hash');
  const type = searchParams.get('type') as EmailOtpType | null;
  const next = searchParams.get('next') ?? '/auth/callback';

  if (!token_hash || !type) {
    return NextResponse.redirect(new URL('/auth/auth-code-error', request.url));
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.verifyOtp({ type, token_hash });

  if (error) {
    return NextResponse.redirect(new URL('/auth/auth-code-error', request.url));
  }

  return NextResponse.redirect(new URL(next, request.url));
}
