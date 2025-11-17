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

// ============================================================================
// CONSTANTS
// ============================================================================

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ============================================================================
// TYPES
// ============================================================================

interface PageProps {
  params: {
    slug: string;
  };
}

interface PaperData {
  paper_id: string;
  title: string | null;
  authors: string | null;
  arxiv_url: string | null;
  five_minute_summary: string | null;
  thumbnail_url: string | null;
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Fetches paper data from the API using the slug
 * @param slug - The paper slug to fetch
 * @returns Paper data or null if not found
 */
async function getPaperData(slug: string): Promise<PaperData | null> {
  try {
    // Resolve slug to paper_uuid
    const slugRes = await fetch(`${API_URL}/papers/slug/${encodeURIComponent(slug)}`, {
      cache: 'no-store',
    });

    if (!slugRes.ok) {
      return null;
    }

    const slugJson = await slugRes.json();
    if (slugJson?.tombstone) {
      return null;
    }

    const uuid = slugJson?.paper_uuid;
    if (!uuid) {
      return null;
    }

    // Fetch paper summary
    const paperRes = await fetch(`${API_URL}/papers/${uuid}/summary`, {
      cache: 'no-store',
    });

    if (!paperRes.ok) {
      return null;
    }

    const paperData = await paperRes.json();
    return {
      paper_id: paperData.paper_id,
      title: paperData.title,
      authors: paperData.authors,
      arxiv_url: paperData.arxiv_url,
      five_minute_summary: paperData.five_minute_summary,
      thumbnail_url: paperData.thumbnail_url,
    };
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
  const paperData = await getPaperData(params.slug);

  if (!paperData) {
    return {
      title: 'Paper Not Found',
    };
  }

  // Extract first 200 characters of summary for description
  const description = paperData.five_minute_summary
    ? paperData.five_minute_summary.substring(0, 200).replace(/[#*`]/g, '') + '...'
    : `Research paper by ${paperData.authors || 'Unknown authors'}`;

  const title = `${paperData.title || 'Research Paper'} - ${paperData.authors?.split(',')[0] || 'Paper Summary'}`;
  const paperUrl = `/paper/${params.slug}`;
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
      images: paperData.thumbnail_url
        ? [
            {
              url: paperData.thumbnail_url,
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
      images: paperData.thumbnail_url ? [paperData.thumbnail_url] : [],
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
  const paperData = await getPaperData(params.slug);

  if (!paperData) {
    notFound();
  }

  return <SharedPaperClient initialPaperData={paperData} slug={params.slug} />;
}
