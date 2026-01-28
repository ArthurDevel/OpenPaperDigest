/**
 * Individual Paper Page
 *
 * Server-side rendered page for displaying individual research papers with full SEO metadata.
 * Responsibilities:
 * - Fetch paper data server-side for SEO
 * - Generate dynamic metadata for search engines and social sharing
 * - Render paper details with client-side interactivity
 */

import { Metadata } from 'next';
import { notFound } from 'next/navigation';
import SharedPaperClient from './SharedPaperClient';
import type { PaperSummary } from '../../../types/paper';

// ============================================================================
// CONSTANTS
// ============================================================================

/**
 * Base URL for internal API calls (server-side)
 * Uses localhost since this runs on the server
 */
const API_BASE = process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000';

// ============================================================================
// TYPES
// ============================================================================

interface PageProps {
  params: Promise<{
    slug: string;
  }>;
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Fetches paper data from the API using the slug
 * @param slug - The paper slug to fetch
 * @returns Paper data or null if not found
 */
async function getPaperData(slug: string): Promise<PaperSummary | null> {
  try {
    // Resolve slug to paperUuid
    const slugRes = await fetch(`${API_BASE}/api/papers/slug/${encodeURIComponent(slug)}`, {
      cache: 'no-store',
    });

    if (!slugRes.ok) {
      return null;
    }

    const slugJson = await slugRes.json();
    if (slugJson?.tombstone) {
      return null;
    }

    const uuid = slugJson?.paperUuid;
    if (!uuid) {
      return null;
    }

    // Fetch paper summary
    const paperRes = await fetch(`${API_BASE}/api/papers/${uuid}/summary`, {
      cache: 'no-store',
    });

    if (!paperRes.ok) {
      return null;
    }

    const paperData = await paperRes.json();
    return paperData as PaperSummary;
  } catch (error) {
    console.error('Error fetching paper data:', error);
    return null;
  }
}

// ============================================================================
// METADATA GENERATION
// ============================================================================

/**
 * Generates SEO metadata for the paper page
 * @param params - Page parameters containing the slug
 * @returns Metadata object for Next.js
 */
export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const resolvedParams = await params;
  const paperData = await getPaperData(resolvedParams.slug);

  if (!paperData) {
    return {
      title: 'Paper Not Found',
    };
  }

  // Extract first 200 characters of summary for description
  const description = paperData.fiveMinuteSummary
    ? paperData.fiveMinuteSummary.substring(0, 200).replace(/[#*`]/g, '') + '...'
    : `Research paper by ${paperData.authors || 'Unknown authors'}`;

  const title = `${paperData.title || 'Research Paper'} - ${paperData.authors?.split(',')[0] || 'Paper Summary'}`;
  const paperUrl = `/paper/${resolvedParams.slug}`;
  const fullUrl = `${process.env.NEXT_PUBLIC_SITE_URL || 'https://openpaperdigest.com'}${paperUrl}`;

  return {
    title,
    description,
    keywords: ['research paper', 'paper summary', paperData.title || '', paperData.authors || '', 'arxiv', 'scientific research'],
    authors: paperData.authors ? paperData.authors.split(',').map((a: string) => ({ name: a.trim() })) : undefined,
    openGraph: {
      title: paperData.title || 'Research Paper',
      description,
      type: 'article',
      url: fullUrl,
      siteName: 'Open Paper Digest',
      locale: 'en_US',
      images: paperData.thumbnailUrl
        ? [
            {
              url: paperData.thumbnailUrl,
              width: 400,
              height: 400,
              alt: paperData.title || 'Paper thumbnail',
            },
          ]
        : [],
    },
    twitter: {
      card: 'summary_large_image',
      title: paperData.title || 'Research Paper',
      description,
      images: paperData.thumbnailUrl ? [paperData.thumbnailUrl] : [],
      creator: '@openpaperdigest',
    },
    alternates: {
      canonical: fullUrl,
    },
  };
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * Paper page component that displays a single paper with full details
 * @param params - Page parameters containing the slug
 * @returns Rendered paper page
 */
export default async function PaperPage({ params }: PageProps) {
  const resolvedParams = await params;
  const paperData = await getPaperData(resolvedParams.slug);

  if (!paperData) {
    notFound();
  }

  return <SharedPaperClient initialPaperData={paperData} slug={resolvedParams.slug} />;
}
