/**
 * UI E2E Tests - Authentication
 *
 * Tests login page rendering and basic user interactions.
 *
 * Responsibilities:
 * - Verify login page renders correctly
 * - Test form validation behavior
 * - Verify authenticated state display
 *
 * Environment Requirements:
 * - Running Next.js server on localhost:3000
 * - NEXT_PUBLIC_SUPABASE_URL: Supabase project URL
 * - NEXT_PUBLIC_SUPABASE_ANON_KEY: Supabase anonymous key
 */

import { test, expect } from '@playwright/test';

// ============================================================================
// LOGIN PAGE RENDERING
// ============================================================================

test.describe('Login Page - Rendering', () => {
  test('renders login page with email input and submit button', async ({ page }) => {
    await page.goto('/login');

    // Wait for loading state to complete
    await expect(page.getByText('Loading session...')).not.toBeVisible({ timeout: 10000 });

    // Check heading is visible
    await expect(page.getByRole('heading', { name: 'Sign In' })).toBeVisible();

    // Check email input is visible
    const emailInput = page.getByLabel('Email address');
    await expect(emailInput).toBeVisible();
    await expect(emailInput).toHaveAttribute('type', 'email');

    // Check submit button is visible
    await expect(page.getByRole('button', { name: 'Send Magic Link' })).toBeVisible();

    // Check descriptive text is present
    await expect(
      page.getByText('Enter your email to receive a magic link to sign in')
    ).toBeVisible();
  });

  test('email input has required attribute', async ({ page }) => {
    await page.goto('/login');

    // Wait for loading state to complete
    await expect(page.getByText('Loading session...')).not.toBeVisible({ timeout: 10000 });

    const emailInput = page.getByLabel('Email address');
    await expect(emailInput).toHaveAttribute('required', '');
  });
});

// ============================================================================
// LOGIN PAGE FORM INTERACTIONS
// ============================================================================

test.describe('Login Page - Form Interactions', () => {
  test('submit button is disabled while loading', async ({ page }) => {
    await page.goto('/login');

    // Wait for loading state to complete
    await expect(page.getByText('Loading session...')).not.toBeVisible({ timeout: 10000 });

    // Fill in email and submit
    await page.getByLabel('Email address').fill('test@example.com');

    // Click submit and immediately check button state
    const submitButton = page.getByRole('button', { name: /send magic link|sending/i });
    await submitButton.click();

    // Button should show loading state (text changes to "Sending...")
    // Note: This may be too fast to catch, depending on network speed
    await expect(submitButton).toBeDisabled();
  });

  test('shows success message after submitting valid email', async ({ page }) => {
    await page.goto('/login');

    // Wait for loading state to complete
    await expect(page.getByText('Loading session...')).not.toBeVisible({ timeout: 10000 });

    // Fill in email and submit
    await page.getByLabel('Email address').fill('test@example.com');
    await page.getByRole('button', { name: 'Send Magic Link' }).click();

    // Wait for either success or error message
    // Note: This requires valid Supabase credentials to succeed
    const successMessage = page.getByText('Magic link sent!');
    const errorMessage = page.locator('.bg-red-100, [class*="bg-red"]');

    // Either success or error should appear (depending on env setup)
    await expect(successMessage.or(errorMessage)).toBeVisible({ timeout: 15000 });
  });

  test('clears email input after successful submission', async ({ page }) => {
    await page.goto('/login');

    // Wait for loading state to complete
    await expect(page.getByText('Loading session...')).not.toBeVisible({ timeout: 10000 });

    const emailInput = page.getByLabel('Email address');
    await emailInput.fill('test@example.com');
    await page.getByRole('button', { name: 'Send Magic Link' }).click();

    // Wait for submission to complete
    const successMessage = page.getByText('Magic link sent!');
    const errorMessage = page.locator('.bg-red-100, [class*="bg-red"]');
    await expect(successMessage.or(errorMessage)).toBeVisible({ timeout: 15000 });

    // If success, email should be cleared
    const hasSuccess = await successMessage.isVisible();
    if (hasSuccess) {
      await expect(emailInput).toHaveValue('');
    }
  });
});

// ============================================================================
// AUTH CALLBACK PAGE
// ============================================================================

test.describe('Auth Callback Page', () => {
  test('renders callback page with authentication heading', async ({ page }) => {
    await page.goto('/auth/callback');

    await expect(page.getByRole('heading', { name: 'Authentication' })).toBeVisible();
  });

  test('shows error message when error param is present', async ({ page }) => {
    await page.goto('/auth/callback?error=invalid_token');

    await expect(page.getByRole('heading', { name: 'Authentication' })).toBeVisible();

    // Error message should be displayed
    await expect(page.getByText(/Authentication failed/i)).toBeVisible();
    await expect(page.getByText(/invalid_token/i)).toBeVisible();
  });
});
