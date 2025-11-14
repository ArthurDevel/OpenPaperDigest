/**
 * Umami Analytics Script Component
 *
 * This component loads the Umami analytics tracking script.
 * It automatically tracks page views and provides privacy-focused analytics.
 *
 * Responsibilities:
 * - Load Umami tracking script from the configured host
 * - Initialize analytics with the website ID
 * - Automatically track page views across the application
 */

import Script from 'next/script';

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * Renders the Umami analytics tracking script.
 * Only renders if NEXT_PUBLIC_UMAMI_WEBSITE_ID is configured.
 *
 * @returns Script element for Umami tracking or null if not configured
 */
export default function UmamiScript() {
  const websiteId = process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID;
  const umamiUrl = process.env.NEXT_PUBLIC_UMAMI_URL || 'http://localhost:3001';

  if (!websiteId) {
    return null;
  }

  return (
    <Script
      defer
      src={`${umamiUrl}/script.js`}
      data-website-id={websiteId}
      strategy="afterInteractive"
    />
  );
}
