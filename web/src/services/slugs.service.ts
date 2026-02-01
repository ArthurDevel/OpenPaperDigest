/**
 * Slug Service
 *
 * Provides business logic for paper slug operations.
 * - Resolves slugs to paper UUIDs
 * - Generates URL-safe slugs from paper titles and authors
 * - Creates and retrieves slugs for papers (idempotent)
 */

import { createClient } from '@/lib/supabase/server';
import type { ResolveSlugResponse } from '@/types/paper';
import type { Tables, TablesInsert } from '@/lib/types/database.types';

// ============================================================================
// CONSTANTS
// ============================================================================

const MAX_SLUG_LENGTH = 200;
const SLUG_SEPARATOR = '-';

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * Resolve a slug to its associated paper UUID.
 * @param slug - The slug to resolve
 * @returns Response with paper UUID, slug, and tombstone status
 */
export async function resolveSlug(slug: string): Promise<ResolveSlugResponse> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from('paper_slugs')
    .select('slug, paper_uuid, tombstone')
    .eq('slug', slug)
    .maybeSingle();

  if (error) {
    throw new Error(error.message);
  }

  const paperSlug = data as Tables<'paper_slugs'> | null;

  if (!paperSlug) {
    return {
      paperUuid: null,
      slug,
      tombstone: false,
    };
  }

  return {
    paperUuid: paperSlug.paper_uuid,
    slug: paperSlug.slug,
    tombstone: paperSlug.tombstone,
  };
}

/**
 * Get the latest non-tombstone slug for a paper.
 * @param paperUuid - The paper UUID
 * @returns Response with slug info, or null paperUuid if no active slug exists
 */
export async function getSlugForPaper(paperUuid: string): Promise<ResolveSlugResponse> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from('paper_slugs')
    .select('slug, paper_uuid, tombstone')
    .eq('paper_uuid', paperUuid)
    .eq('tombstone', false)
    .order('created_at', { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error) {
    throw new Error(error.message);
  }

  const paperSlug = data as Tables<'paper_slugs'> | null;

  if (!paperSlug) {
    return {
      paperUuid: null,
      slug: '',
      tombstone: false,
    };
  }

  return {
    paperUuid: paperSlug.paper_uuid,
    slug: paperSlug.slug,
    tombstone: paperSlug.tombstone,
  };
}

/**
 * Create a slug for a paper. Idempotent - returns existing slug if one exists.
 * Fetches paper title and authors to generate the slug.
 * @param paperUuid - The paper UUID
 * @returns Response with the created or existing slug
 */
export async function createSlug(paperUuid: string): Promise<ResolveSlugResponse> {
  const supabase = await createClient();

  // Check if a non-tombstone slug already exists
  const existing = await getSlugForPaper(paperUuid);
  if (existing.paperUuid && existing.slug) {
    return existing;
  }

  // Fetch paper to get title and authors
  const { data: paperData, error: paperError } = await supabase
    .from('papers')
    .select('title, authors')
    .eq('paper_uuid', paperUuid)
    .maybeSingle();

  if (paperError) {
    throw new Error(paperError.message);
  }

  const paper = paperData as Tables<'papers'> | null;

  if (!paper) {
    throw new Error(`Paper not found: ${paperUuid}`);
  }

  // Generate the slug
  const slug = buildPaperSlug(paper.title, paper.authors);

  // Check if the slug already exists (might be tombstoned or belong to another paper)
  const { data: existingSlugData, error: existingSlugError } = await supabase
    .from('paper_slugs')
    .select('slug, paper_uuid, tombstone')
    .eq('slug', slug)
    .maybeSingle();

  if (existingSlugError) {
    throw new Error(existingSlugError.message);
  }

  const existingSlug = existingSlugData as Tables<'paper_slugs'> | null;

  if (existingSlug) {
    // If it's for this paper and active, return it
    if (existingSlug.paper_uuid === paperUuid && !existingSlug.tombstone) {
      return {
        paperUuid: existingSlug.paper_uuid,
        slug: existingSlug.slug,
        tombstone: existingSlug.tombstone,
      };
    }

    // Slug belongs to another paper or is tombstoned - append UUID suffix
    const uniqueSlug = `${slug}${SLUG_SEPARATOR}${paperUuid.slice(0, 8)}`;
    const insertData: TablesInsert<'paper_slugs'> = {
      slug: uniqueSlug,
      paper_uuid: paperUuid,
      tombstone: false,
      created_at: new Date().toISOString(),
    };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { data: createdData, error: createError } = await (supabase
      .from('paper_slugs') as any)
      .insert(insertData)
      .select('slug, paper_uuid, tombstone')
      .single();

    if (createError) {
      throw new Error(createError.message);
    }

    const created = createdData as Tables<'paper_slugs'>;

    return {
      paperUuid: created.paper_uuid,
      slug: created.slug,
      tombstone: created.tombstone,
    };
  }

  // Create the new slug
  const newSlugData: TablesInsert<'paper_slugs'> = {
    slug,
    paper_uuid: paperUuid,
    tombstone: false,
    created_at: new Date().toISOString(),
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: createdData, error: createError } = await (supabase
    .from('paper_slugs') as any)
    .insert(newSlugData)
    .select('slug, paper_uuid, tombstone')
    .single();

  if (createError) {
    throw new Error(createError.message);
  }

  const created = createdData as Tables<'paper_slugs'>;

  return {
    paperUuid: created.paper_uuid,
    slug: created.slug,
    tombstone: created.tombstone,
  };
}

/**
 * Generate a URL-safe slug from paper title and authors.
 * Format: {sanitized-title}-{first-author-lastname}
 * @param title - Paper title (may be null)
 * @param authors - Comma-separated author names (may be null)
 * @returns URL-safe slug string
 */
export function buildPaperSlug(title: string | null, authors: string | null): string {
  const titlePart = sanitizeForSlug(title ?? 'untitled');
  const authorPart = extractFirstAuthorLastName(authors);

  let slug = titlePart;
  if (authorPart) {
    slug = `${titlePart}${SLUG_SEPARATOR}${authorPart}`;
  }

  // Ensure slug doesn't exceed max length
  if (slug.length > MAX_SLUG_LENGTH) {
    slug = slug.slice(0, MAX_SLUG_LENGTH);
    // Remove trailing separator if truncation left one
    if (slug.endsWith(SLUG_SEPARATOR)) {
      slug = slug.slice(0, -1);
    }
  }

  return slug;
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Sanitizes a string for use in a URL slug.
 * Converts to lowercase, replaces spaces with hyphens, removes special characters.
 * @param text - Text to sanitize
 * @returns Sanitized slug-safe string
 */
function sanitizeForSlug(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/\s+/g, SLUG_SEPARATOR) // Replace spaces with separator
    .replace(/[^a-z0-9-]/g, '') // Remove non-alphanumeric except hyphens
    .replace(/-+/g, SLUG_SEPARATOR) // Collapse multiple hyphens
    .replace(/^-|-$/g, ''); // Remove leading/trailing hyphens
}

/**
 * Extracts the last name of the first author from a comma-separated author string.
 * @param authors - Comma-separated author names (e.g., "John Smith, Jane Doe")
 * @returns Sanitized first author's last name or empty string
 */
function extractFirstAuthorLastName(authors: string | null): string {
  if (!authors) {
    return '';
  }

  // Get first author (before first comma)
  const firstAuthor = authors.split(',')[0].trim();
  if (!firstAuthor) {
    return '';
  }

  // Get last word (assumed to be last name)
  const nameParts = firstAuthor.split(/\s+/);
  const lastName = nameParts[nameParts.length - 1];

  return sanitizeForSlug(lastName);
}
