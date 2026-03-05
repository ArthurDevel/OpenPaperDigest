/**
 * Supabase Storage Helpers
 *
 * Server-side utility functions for reading and managing paper assets
 * stored in the private Supabase Storage "papers" bucket.
 *
 * Responsibilities:
 * - Generate signed URLs for thumbnails and figure images (private bucket)
 * - Download paper content (markdown, sections, figures metadata, metadata) via Supabase client
 * - Delete all storage assets for a paper (requires service role key)
 */

import { createClient as createSupabaseClient } from '@supabase/supabase-js';

// ============================================================================
// CONSTANTS
// ============================================================================

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const BUCKET_NAME = 'papers';
const SIGNED_URL_EXPIRY_SECONDS = 3600;

// ============================================================================
// TYPES
// ============================================================================

/** Content downloaded from storage for a single paper. */
export interface StoredPaperContent {
  finalMarkdown: string;
  sections: Record<string, unknown>[];
  figures: Record<string, unknown>[];
  metadata: Record<string, unknown>;
}

// ============================================================================
// SERVICE CLIENT
// ============================================================================

/**
 * Create a Supabase client using the service role key.
 * Required for all private bucket operations (signed URLs, downloads, deletes).
 * @returns Supabase client with service role permissions
 */
function getServiceClient() {
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!serviceRoleKey) {
    throw new Error('SUPABASE_SERVICE_ROLE_KEY is not set -- cannot access private storage bucket');
  }
  return createSupabaseClient(SUPABASE_URL, serviceRoleKey);
}

// ============================================================================
// SIGNED URL HELPERS
// ============================================================================

/**
 * Generate a signed URL for a paper's thumbnail image.
 * Returns null if the thumbnail doesn't exist in storage.
 * @param paperUuid - Unique identifier for the paper
 * @returns Signed HTTPS URL for thumbnail.png (valid for 1 hour), or null
 */
export async function getPaperThumbnailUrl(paperUuid: string): Promise<string | null> {
  const supabase = getServiceClient();
  const path = `${paperUuid}/thumbnail.png`;

  const { data, error } = await supabase.storage
    .from(BUCKET_NAME)
    .createSignedUrl(path, SIGNED_URL_EXPIRY_SECONDS);

  if (error || !data?.signedUrl) {
    return null;
  }

  return data.signedUrl;
}

/**
 * Generate signed thumbnail URLs for multiple papers in a single API call.
 * Returns a Map of paperUuid -> signedUrl (null for missing thumbnails).
 * @param paperUuids - Array of paper UUIDs
 * @returns Map from paperUuid to signed URL or null
 */
export async function getPaperThumbnailUrls(
  paperUuids: string[]
): Promise<Map<string, string | null>> {
  if (paperUuids.length === 0) return new Map();

  const supabase = getServiceClient();
  const paths = paperUuids.map((uuid) => `${uuid}/thumbnail.png`);

  const { data, error } = await supabase.storage
    .from(BUCKET_NAME)
    .createSignedUrls(paths, SIGNED_URL_EXPIRY_SECONDS);

  const result = new Map<string, string | null>();

  if (error || !data) {
    for (const uuid of paperUuids) result.set(uuid, null);
    return result;
  }

  for (let i = 0; i < paperUuids.length; i++) {
    const entry = data[i];
    result.set(paperUuids[i], entry?.error ? null : (entry?.signedUrl ?? null));
  }

  return result;
}

/**
 * Generate a signed URL for a specific figure image.
 * @param paperUuid - Unique identifier for the paper
 * @param figureId - The figure identifier (filename without extension)
 * @returns Signed HTTPS URL for the figure PNG (valid for 1 hour)
 */
export async function getPaperFigureUrl(paperUuid: string, figureId: string): Promise<string> {
  const supabase = getServiceClient();
  const path = `${paperUuid}/figures/${figureId}.png`;

  const { data, error } = await supabase.storage
    .from(BUCKET_NAME)
    .createSignedUrl(path, SIGNED_URL_EXPIRY_SECONDS);

  if (error || !data?.signedUrl) {
    throw new Error(`Failed to generate signed URL for ${path}: ${error?.message ?? 'no signed URL returned'}`);
  }

  return data.signedUrl;
}

// ============================================================================
// DOWNLOAD HELPERS
// ============================================================================

/**
 * Download all text/JSON content for a paper from storage.
 * Downloads content.md, sections.json, figures.json, and metadata.json
 * using the authenticated Supabase client (service role key).
 * @param paperUuid - Unique identifier for the paper
 * @returns StoredPaperContent with all text content fields populated
 */
export async function downloadPaperContent(paperUuid: string): Promise<StoredPaperContent> {
  const supabase = getServiceClient();
  const bucket = supabase.storage.from(BUCKET_NAME);
  const prefix = paperUuid;

  // Download all four files in parallel
  const [markdownResult, sectionsResult, figuresResult, metadataResult] = await Promise.all([
    bucket.download(`${prefix}/content.md`),
    bucket.download(`${prefix}/sections.json`),
    bucket.download(`${prefix}/figures.json`),
    bucket.download(`${prefix}/metadata.json`),
  ]);

  if (markdownResult.error || !markdownResult.data) {
    throw new Error(`Failed to download content.md for paper ${paperUuid}: ${markdownResult.error?.message}`);
  }
  if (sectionsResult.error || !sectionsResult.data) {
    throw new Error(`Failed to download sections.json for paper ${paperUuid}: ${sectionsResult.error?.message}`);
  }
  if (figuresResult.error || !figuresResult.data) {
    throw new Error(`Failed to download figures.json for paper ${paperUuid}: ${figuresResult.error?.message}`);
  }
  if (metadataResult.error || !metadataResult.data) {
    throw new Error(`Failed to download metadata.json for paper ${paperUuid}: ${metadataResult.error?.message}`);
  }

  // Parse blob contents
  const [finalMarkdown, sectionsText, figuresText, metadataText] = await Promise.all([
    markdownResult.data.text(),
    sectionsResult.data.text(),
    figuresResult.data.text(),
    metadataResult.data.text(),
  ]);

  return {
    finalMarkdown,
    sections: JSON.parse(sectionsText) as Record<string, unknown>[],
    figures: JSON.parse(figuresText) as Record<string, unknown>[],
    metadata: JSON.parse(metadataText) as Record<string, unknown>,
  };
}

/**
 * Download only the markdown content for a paper.
 * Uses the authenticated Supabase client (service role key).
 * @param paperUuid - Unique identifier for the paper
 * @returns The raw markdown string from content.md
 */
export async function downloadPaperMarkdown(paperUuid: string): Promise<string> {
  const supabase = getServiceClient();

  const { data, error } = await supabase.storage
    .from(BUCKET_NAME)
    .download(`${paperUuid}/content.md`);

  if (error || !data) {
    throw new Error(`Failed to download content.md for paper ${paperUuid}: ${error?.message}`);
  }

  return data.text();
}

// ============================================================================
// DELETE HELPERS
// ============================================================================

/**
 * Delete all storage files for a paper.
 * Uses a service-role Supabase client since delete requires elevated permissions.
 * Reads figures.json first to discover individual figure file paths.
 * @param paperUuid - Unique identifier for the paper
 */
export async function deletePaperAssets(paperUuid: string): Promise<void> {
  const supabase = getServiceClient();
  const bucket = supabase.storage.from(BUCKET_NAME);
  const prefix = paperUuid;

  // Collect known top-level paths
  const pathsToDelete = [
    `${prefix}/thumbnail.png`,
    `${prefix}/content.md`,
    `${prefix}/sections.json`,
    `${prefix}/figures.json`,
    `${prefix}/metadata.json`,
  ];

  // Try to read figures.json to find individual figure files
  try {
    const { data: figuresBlob, error: figuresError } = await bucket.download(`${prefix}/figures.json`);
    if (!figuresError && figuresBlob) {
      const figuresText = await figuresBlob.text();
      const figuresList = JSON.parse(figuresText) as Record<string, unknown>[];
      for (const fig of figuresList) {
        const identifier = fig.identifier as string | undefined;
        if (identifier) {
          pathsToDelete.push(`${prefix}/figures/${identifier}.png`);
        }
      }
    }
  } catch {
    // If figures.json doesn't exist or is malformed, skip figure path discovery.
    // Top-level files will still be cleaned up.
  }

  const { error } = await bucket.remove(pathsToDelete);
  if (error) {
    throw new Error(`Failed to delete storage assets for paper ${paperUuid}: ${error.message}`);
  }
}
