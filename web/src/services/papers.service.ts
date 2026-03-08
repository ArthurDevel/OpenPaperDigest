/**
 * Paper Service
 *
 * Provides business logic for paper-related operations.
 * - CRUD operations for papers (list, get by uuid/slug, summary, content)
 * - arXiv paper checking and enqueuing
 * - Paper content retrieval from Supabase Storage
 * - Paper JSON import functionality
 */

import { createClient } from '@/lib/supabase/server';
import { normalizeId } from '@/lib/arxiv';
import * as slugsService from '@/services/slugs.service';
import {
  getPaperThumbnailUrl,
  getPaperFigureUrl,
  downloadPaperContent,
  downloadPaperMarkdown,
  deletePaperAssets,
} from '@/lib/supabase/storage';
import type {
  Paper,
  MinimalPaper,
  PaginatedMinimalPapers,
  PaperSummary,
  CheckArxivResponse,
  EnqueueArxivResponse,
  JobDbStatus,
  PaperStatus,
  ProcessingMetrics,
} from '@/types/paper';
import type { Tables, TablesInsert, TablesUpdate } from '@/lib/types/database.types';
import { randomUUID } from 'crypto';
import { writeFile, mkdir } from 'fs/promises';
import path from 'path';

// ============================================================================
// CONSTANTS
// ============================================================================

const DEFAULT_PAGE = 1;
const DEFAULT_LIMIT = 20;
const BASE_VIEWER_URL = '/paper';

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * Get a paginated list of papers with minimal fields for display.
 * Includes the latest non-tombstone slug for each paper.
 * @param page - Page number (1-indexed), defaults to 1
 * @param limit - Number of items per page, defaults to 20
 * @returns Paginated list of minimal paper data
 */
export async function listMinimalPapers(
  page: number = DEFAULT_PAGE,
  limit: number = DEFAULT_LIMIT
): Promise<PaginatedMinimalPapers> {
  const supabase = await createClient();
  const offset = (page - 1) * limit;

  // Fetch limit+1 to detect hasMore without expensive count query
  const { data: papersData, error: papersError } = await supabase
    .from('papers')
    .select('paper_uuid, title, authors')
    .in('status', ['completed', 'partially_completed'])
    .order('finished_at', { ascending: false })
    .range(offset, offset + limit);

  if (papersError) throw new Error(papersError.message);

  type MinimalPaperRow = Pick<Tables<'papers'>, 'paper_uuid' | 'title' | 'authors'>;
  const allPapers = (papersData ?? []) as MinimalPaperRow[];
  const hasMore = allPapers.length > limit;
  const papers = hasMore ? allPapers.slice(0, limit) : allPapers;

  // Get paper_uuids to fetch slugs separately
  const paperUuids = papers.map((p) => p.paper_uuid);

  // Fetch active slugs - only need slug and paper_uuid fields
  const { data: slugsData, error: slugsError } = await supabase
    .from('paper_slugs')
    .select('paper_uuid, slug')
    .in('paper_uuid', paperUuids)
    .eq('tombstone', false)
    .order('created_at', { ascending: false });

  if (slugsError) throw new Error(slugsError.message);

  type SlugRow = Pick<Tables<'paper_slugs'>, 'paper_uuid' | 'slug'>;
  const slugs = (slugsData ?? []) as SlugRow[];

  // Build a map of paper_uuid -> most recent slug
  const slugMap = new Map<string, string>();
  for (const slug of slugs) {
    if (slug.paper_uuid && !slugMap.has(slug.paper_uuid)) {
      slugMap.set(slug.paper_uuid, slug.slug);
    }
  }

  // Generate signed thumbnail URLs in parallel
  const items: MinimalPaper[] = await Promise.all(
    papers.map(async (paper) => ({
      paperUuid: paper.paper_uuid,
      title: paper.title,
      authors: paper.authors,
      slug: slugMap.get(paper.paper_uuid) ?? null,
      thumbnailUrl: await getPaperThumbnailUrl(paper.paper_uuid),
    }))
  );

  return {
    items,
    page,
    limit,
    hasMore,
  };
}

/**
 * Get a full paper record by UUID.
 * @param uuid - The paper UUID
 * @returns Full paper record or null if not found
 */
export async function getPaperByUuid(uuid: string): Promise<Paper | null> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from('papers')
    .select('*')
    .eq('paper_uuid', uuid)
    .maybeSingle();

  if (error) throw new Error(error.message);

  const paper = data as Tables<'papers'> | null;

  if (!paper) {
    return null;
  }

  return await mapDbRowToApiPaper(paper);
}

/**
 * Get a paper by resolving its slug first.
 * @param slug - The paper slug
 * @returns Full paper record or null if slug not found or tombstoned
 */
export async function getPaperBySlug(slug: string): Promise<Paper | null> {
  const resolved = await slugsService.resolveSlug(slug);

  if (!resolved.paperUuid || resolved.tombstone) {
    return null;
  }

  return getPaperByUuid(resolved.paperUuid);
}

/**
 * Get a lightweight paper summary for quick display.
 * @param uuid - The paper UUID
 * @returns Paper summary or throws if not found
 */
export async function getPaperSummary(uuid: string): Promise<PaperSummary> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from('papers')
    .select(`
      paper_uuid,
      title,
      authors,
      arxiv_url,
      summaries,
      num_pages
    `)
    .eq('paper_uuid', uuid)
    .maybeSingle();

  if (error) throw new Error(error.message);

  const paper = data as Tables<'papers'> | null;

  if (!paper) {
    throw new Error(`Paper not found: ${uuid}`);
  }

  // Read five_minute_summary from the summaries JSON column
  const summaries = paper.summaries as Record<string, string> | null;
  const fiveMinuteSummary = summaries?.five_minute_summary ?? null;

  return {
    paperId: paper.paper_uuid,
    title: paper.title,
    authors: paper.authors,
    arxivUrl: paper.arxiv_url,
    fiveMinuteSummary,
    pageCount: paper.num_pages ?? 0,
    thumbnailUrl: await getPaperThumbnailUrl(paper.paper_uuid),
  };
}

/**
 * Get the raw markdown content for a paper from Supabase Storage.
 * @param uuid - The paper UUID
 * @returns Markdown string or throws if not found
 */
export async function getPaperMarkdown(uuid: string): Promise<string> {
  const supabase = await createClient();

  // Verify paper exists in DB
  const { data, error } = await supabase
    .from('papers')
    .select('paper_uuid')
    .eq('paper_uuid', uuid)
    .maybeSingle();

  if (error) throw new Error(error.message);

  if (!data) {
    throw new Error(`Paper not found: ${uuid}`);
  }

  return downloadPaperMarkdown(uuid);
}

/**
 * Get the full processed content JSON for a paper.
 * Fetches metadata from DB and content from Supabase Storage.
 * Figures use public storage URLs instead of base64.
 * @param uuid - The paper UUID
 * @returns Assembled paper content object or throws if not found
 */
export async function getPaperJson(uuid: string): Promise<Record<string, unknown>> {
  const supabase = await createClient();

  // Fetch paper metadata from DB
  const { data, error } = await supabase
    .from('papers')
    .select(`
      paper_uuid,
      title,
      authors,
      arxiv_url,
      processing_time_seconds
    `)
    .eq('paper_uuid', uuid)
    .maybeSingle();

  if (error) throw new Error(error.message);

  const paper = data as Tables<'papers'> | null;

  if (!paper) {
    throw new Error(`Paper not found: ${uuid}`);
  }

  // Download content from Supabase Storage
  const storedContent = await downloadPaperContent(uuid);

  // Build figure objects with signed storage URLs in parallel
  const figures = await Promise.all(
    storedContent.figures.map(async (fig) => ({
      ...fig,
      imageUrl: await getPaperFigureUrl(uuid, fig.identifier as string),
    }))
  );

  // Return combined data with paper metadata and storage content
  return {
    paperId: paper.paper_uuid,
    title: paper.title,
    authors: paper.authors,
    arxivUrl: paper.arxiv_url,
    thumbnailUrl: await getPaperThumbnailUrl(uuid),
    processingTimeSeconds: paper.processing_time_seconds,
    final_markdown: storedContent.finalMarkdown,
    sections: storedContent.sections,
    figures,
    usage_summary: storedContent.metadata,
  };
}

/**
 * Count completed papers since a given timestamp.
 * @param since - Timestamp to count from
 * @returns Number of completed papers since the timestamp
 */
export async function countPapersSince(since: Date): Promise<number> {
  const supabase = await createClient();

  const { count, error } = await supabase
    .from('papers')
    .select('*', { count: 'exact', head: true })
    .in('status', ['completed', 'partially_completed'])
    .gte('finished_at', since.toISOString());

  if (error) throw new Error(error.message);

  return count ?? 0;
}

/**
 * Check if an arXiv paper exists and is processed.
 * @param arxivIdOrUrl - arXiv ID or URL to check
 * @returns Object with exists flag and viewer URL if found
 */
export async function checkArxivExists(arxivIdOrUrl: string): Promise<CheckArxivResponse> {
  const supabase = await createClient();

  // Normalize the arXiv ID
  const { arxivId } = normalizeId(arxivIdOrUrl);

  // Look up paper by arXiv ID
  const { data: paperData, error } = await supabase
    .from('papers')
    .select('paper_uuid, status')
    .eq('arxiv_id', arxivId)
    .maybeSingle();

  if (error) throw new Error(error.message);

  const paper = paperData as Tables<'papers'> | null;

  if (!paper || !['completed', 'partially_completed'].includes(paper.status)) {
    return { exists: false, viewerUrl: null };
  }

  // Fetch the most recent active slug for this paper
  const { data: slugData, error: slugsError } = await supabase
    .from('paper_slugs')
    .select('slug')
    .eq('paper_uuid', paper.paper_uuid)
    .eq('tombstone', false)
    .order('created_at', { ascending: false })
    .limit(1)
    .maybeSingle();

  if (slugsError) throw new Error(slugsError.message);

  const slug = (slugData as { slug: string } | null)?.slug;

  // Build viewer URL using slug if available, otherwise UUID
  const viewerUrl = slug ? `${BASE_VIEWER_URL}/${slug}` : `${BASE_VIEWER_URL}/${paper.paper_uuid}`;

  return { exists: true, viewerUrl };
}

/**
 * Create a paper record for arXiv processing.
 * @param url - arXiv URL or ID to enqueue
 * @returns Created job information
 */
export async function enqueueArxiv(url: string): Promise<EnqueueArxivResponse> {
  const supabase = await createClient();

  // Normalize and validate the arXiv ID
  const { arxivId, version } = normalizeId(url);

  // Check if paper already exists
  const { data: existingData, error: existingError } = await supabase
    .from('papers')
    .select('id, paper_uuid, status')
    .eq('arxiv_id', arxivId)
    .maybeSingle();

  if (existingError) throw new Error(existingError.message);

  const existing = existingData as Tables<'papers'> | null;

  if (existing) {
    return {
      jobDbId: Number(existing.id),
      paperUuid: existing.paper_uuid,
      status: existing.status,
    };
  }

  // Create new paper record
  const paperUuid = randomUUID();
  const now = new Date().toISOString();

  const insertData: TablesInsert<'papers'> = {
    paper_uuid: paperUuid,
    arxiv_id: arxivId,
    arxiv_version: version,
    arxiv_url: `https://arxiv.org/abs/${arxivId}${version ?? ''}`,
    status: 'not_started',
    created_at: now,
    updated_at: now,
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: paperData, error: createError } = await (supabase
    .from('papers') as any)
    .insert(insertData)
    .select()
    .single();

  if (createError) throw new Error(createError.message);

  const paper = paperData as Tables<'papers'>;

  return {
    jobDbId: Number(paper.id),
    paperUuid: paper.paper_uuid,
    status: paper.status,
  };
}

/**
 * Import a paper JSON and write it to the paperjsons directory.
 * Creates or updates the paper record in the database.
 * Content is stored in Supabase Storage (uploaded by the worker during processing).
 * @param paper - Paper JSON object with paper_uuid and other fields
 * @returns Job status information
 */
export async function importPaperJson(
  paper: Record<string, unknown>
): Promise<JobDbStatus> {
  const supabase = await createClient();

  // Validate required fields
  const paperUuid = paper.paper_uuid as string | undefined;
  if (!paperUuid) {
    throw new Error('paper_uuid is required');
  }

  // Write JSON to file
  const dataDir = path.join(process.cwd(), 'data', 'paperjsons');
  await mkdir(dataDir, { recursive: true });

  const filePath = path.join(dataDir, `${paperUuid}.json`);
  await writeFile(filePath, JSON.stringify(paper, null, 2), 'utf-8');

  // Check if paper already exists
  const { data: existingData, error: existingError } = await supabase
    .from('papers')
    .select('id')
    .eq('paper_uuid', paperUuid)
    .maybeSingle();

  if (existingError) throw new Error(existingError.message);

  const existing = existingData as Tables<'papers'> | null;

  const now = new Date().toISOString();

  // Extract five_minute_summary into summaries column (may be nested under processed_content in legacy import JSONs)
  const importContent = paper.processed_content as Record<string, unknown> | undefined;
  const fiveMinuteSummary = importContent?.five_minute_summary as string | undefined;
  const summaries = fiveMinuteSummary ? { five_minute_summary: fiveMinuteSummary } : null;

  // Note: processed_content and thumbnail_data_url are no longer written to DB.
  // The worker uploads content to Supabase Storage during processing.
  const updateData: TablesUpdate<'papers'> = {
    arxiv_id: (paper.arxiv_id as string) ?? null,
    arxiv_version: (paper.arxiv_version as string) ?? null,
    arxiv_url: (paper.arxiv_url as string) ?? null,
    title: (paper.title as string) ?? null,
    authors: (paper.authors as string) ?? null,
    status: 'completed',
    num_pages: (paper.num_pages as number) ?? null,
    summaries,
    finished_at: now,
    updated_at: now,
  };

  let dbPaper: Tables<'papers'>;

  if (existing) {
    // Update existing paper
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { data, error } = await (supabase
      .from('papers') as any)
      .update(updateData)
      .eq('paper_uuid', paperUuid)
      .select()
      .single();

    if (error) throw new Error(error.message);
    dbPaper = data as Tables<'papers'>;
  } else {
    // Insert new paper
    const insertData: TablesInsert<'papers'> = {
      paper_uuid: paperUuid,
      created_at: now,
      status: 'completed',
      arxiv_id: (paper.arxiv_id as string) ?? null,
      arxiv_version: (paper.arxiv_version as string) ?? null,
      arxiv_url: (paper.arxiv_url as string) ?? null,
      title: (paper.title as string) ?? null,
      authors: (paper.authors as string) ?? null,
      num_pages: (paper.num_pages as number) ?? null,
      summaries,
      finished_at: now,
      updated_at: now,
    };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { data, error } = await (supabase
      .from('papers') as any)
      .insert(insertData)
      .select()
      .single();

    if (error) throw new Error(error.message);
    dbPaper = data as Tables<'papers'>;
  }

  return await mapDbRowToJobDbStatus(dbPaper);
}

// ============================================================================
// ADMIN HANDLERS
// ============================================================================

/**
 * Get all papers for admin listing (includes all statuses, not just completed).
 * @param statusFilter - Optional comma-separated list of statuses to filter by
 * @param limit - Maximum number of papers to return, defaults to 500
 * @returns Array of paper job status objects
 */
export async function listAllPapers(
  statusFilter?: string,
  limit: number = 500
): Promise<JobDbStatus[]> {
  const supabase = await createClient();

  // Parse status filter if provided
  const statuses = statusFilter
    ? statusFilter.split(',').map((s) => s.trim()).filter(Boolean)
    : null;

  let query = supabase
    .from('papers')
    .select(`
      paper_uuid,
      status,
      error_message,
      created_at,
      updated_at,
      started_at,
      finished_at,
      arxiv_id,
      arxiv_version,
      arxiv_url,
      title,
      authors,
      num_pages,
      processing_time_seconds,
      total_cost,
      avg_cost_per_page
    `)
    .order('created_at', { ascending: false })
    .limit(limit);

  if (statuses && statuses.length > 0) {
    query = query.in('status', statuses);
  }

  const { data: papersData, error } = await query;

  if (error) throw new Error(error.message);

  const papers = (papersData ?? []) as Tables<'papers'>[];

  // Generate signed thumbnail URLs in parallel
  return Promise.all(
    papers.map(async (paper) => ({
      paperUuid: paper.paper_uuid,
      status: paper.status as PaperStatus,
      errorMessage: paper.error_message,
      createdAt: new Date(paper.created_at),
      updatedAt: new Date(paper.updated_at),
      startedAt: paper.started_at ? new Date(paper.started_at) : null,
      finishedAt: paper.finished_at ? new Date(paper.finished_at) : null,
      arxivId: paper.arxiv_id,
      arxivVersion: paper.arxiv_version,
      arxivUrl: paper.arxiv_url,
      title: paper.title,
      authors: paper.authors,
      numPages: paper.num_pages,
      thumbnailUrl: await getPaperThumbnailUrl(paper.paper_uuid),
      processingTimeSeconds: paper.processing_time_seconds,
      totalCost: paper.total_cost,
      avgCostPerPage: paper.avg_cost_per_page,
    }))
  );
}

/**
 * Delete a paper by UUID.
 * Removes storage assets and the paper record + associated slugs from the database.
 * Storage deletion is best-effort: if it fails, DB deletion still proceeds.
 * @param uuid - The paper UUID to delete
 * @returns True if paper was deleted, false if not found
 */
export async function deletePaper(uuid: string): Promise<boolean> {
  const supabase = await createClient();

  const { data: paperData, error: findError } = await supabase
    .from('papers')
    .select('id')
    .eq('paper_uuid', uuid)
    .maybeSingle();

  if (findError) throw new Error(findError.message);

  const paper = paperData as Tables<'papers'> | null;

  if (!paper) {
    return false;
  }

  // Delete storage assets first (best-effort -- don't block DB deletion)
  try {
    await deletePaperAssets(uuid);
  } catch (storageError) {
    console.error(`Failed to delete storage assets for paper ${uuid}:`, storageError);
  }

  // Delete associated slugs first (foreign key constraint)
  const { error: slugsError } = await supabase
    .from('paper_slugs')
    .delete()
    .eq('paper_uuid', uuid);

  if (slugsError) throw new Error(slugsError.message);

  // Delete the paper
  const { error: deleteError } = await supabase
    .from('papers')
    .delete()
    .eq('paper_uuid', uuid);

  if (deleteError) throw new Error(deleteError.message);

  return true;
}

/**
 * Restart paper processing by resetting its status.
 * Sets status to 'not_started' and clears error/timing fields.
 * @param uuid - The paper UUID to restart
 * @returns Updated job status or throws if paper not found or already processing
 */
export async function restartPaper(uuid: string): Promise<JobDbStatus> {
  const supabase = await createClient();

  const { data: paperData, error: findError } = await supabase
    .from('papers')
    .select('id, status')
    .eq('paper_uuid', uuid)
    .maybeSingle();

  if (findError) throw new Error(findError.message);

  const paper = paperData as Tables<'papers'> | null;

  if (!paper) {
    throw new Error(`Paper not found: ${uuid}`);
  }

  if (paper.status === 'processing') {
    throw new Error('Paper is already processing');
  }

  // Reset paper for reprocessing
  const resetData: TablesUpdate<'papers'> = {
    status: 'not_started',
    error_message: null,
    started_at: null,
    finished_at: null,
    updated_at: new Date().toISOString(),
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: updatedData, error: updateError } = await (supabase
    .from('papers') as any)
    .update(resetData)
    .eq('paper_uuid', uuid)
    .select(`
      paper_uuid,
      status,
      error_message,
      created_at,
      updated_at,
      started_at,
      finished_at,
      arxiv_id,
      arxiv_version,
      arxiv_url,
      title,
      authors,
      num_pages,
      processing_time_seconds,
      total_cost,
      avg_cost_per_page
    `)
    .single();

  if (updateError) throw new Error(updateError.message);

  const updated = updatedData as Tables<'papers'>;

  return {
    paperUuid: updated.paper_uuid,
    status: updated.status as PaperStatus,
    errorMessage: updated.error_message,
    createdAt: new Date(updated.created_at),
    updatedAt: new Date(updated.updated_at),
    startedAt: updated.started_at ? new Date(updated.started_at) : null,
    finishedAt: updated.finished_at ? new Date(updated.finished_at) : null,
    arxivId: updated.arxiv_id,
    arxivVersion: updated.arxiv_version,
    arxivUrl: updated.arxiv_url,
    title: updated.title,
    authors: updated.authors,
    numPages: updated.num_pages,
    thumbnailUrl: await getPaperThumbnailUrl(updated.paper_uuid),
    processingTimeSeconds: updated.processing_time_seconds,
    totalCost: updated.total_cost,
    avgCostPerPage: updated.avg_cost_per_page,
  };
}

/**
 * Get processing metrics for a paper (admin version, no user check).
 * @param uuid - The paper UUID
 * @returns Processing metrics or throws if paper not found
 */
export async function getProcessingMetricsAdmin(
  uuid: string
): Promise<ProcessingMetrics> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from('papers')
    .select(`
      paper_uuid,
      status,
      num_pages,
      processing_time_seconds,
      total_cost,
      avg_cost_per_page,
      started_at,
      finished_at,
      error_message
    `)
    .eq('paper_uuid', uuid)
    .maybeSingle();

  if (error) throw new Error(error.message);

  const paper = data as Tables<'papers'> | null;

  if (!paper) {
    throw new Error(`Paper not found: ${uuid}`);
  }

  return {
    paperUuid: paper.paper_uuid,
    status: paper.status as PaperStatus,
    numPages: paper.num_pages,
    processingTimeSeconds: paper.processing_time_seconds,
    totalCost: paper.total_cost,
    avgCostPerPage: paper.avg_cost_per_page,
    startedAt: paper.started_at ? new Date(paper.started_at) : null,
    finishedAt: paper.finished_at ? new Date(paper.finished_at) : null,
    errorMessage: paper.error_message,
  };
}

/** Daily paper statistics for a single day */
export interface CumulativeDailyItem {
  date: string;
  dailyCount: number;
  cumulativeCount: number;
  cumulativeFailed: number;
  cumulativeProcessed: number;
  cumulativeNotStarted: number;
  cumulativeProcessing: number;
}

/**
 * Get cumulative daily paper statistics for charting.
 * Uses historical snapshots for past dates and live inference for recent dates.
 * @returns Array of daily statistics from first paper to today
 */
export async function getCumulativeDailyStats(): Promise<CumulativeDailyItem[]> {
  const supabase = await createClient();

  // Check if there are any papers
  const { count: paperCount, error: countError } = await supabase
    .from('papers')
    .select('*', { count: 'exact', head: true });

  if (countError) throw new Error(countError.message);

  if (!paperCount || paperCount === 0) {
    return [];
  }

  // Get latest snapshot date from history table
  const { data: latestSnapshotData, error: snapshotError } = await supabase
    .from('paper_status_history')
    .select('date')
    .order('date', { ascending: false })
    .limit(1)
    .maybeSingle();

  if (snapshotError) throw new Error(snapshotError.message);

  const latestSnapshot = latestSnapshotData as Tables<'paper_status_history'> | null;
  const latestSnapshotDate = latestSnapshot?.date ? new Date(latestSnapshot.date) : null;

  // Get earliest paper creation date
  const { data: earliestPaperData, error: earliestError } = await supabase
    .from('papers')
    .select('created_at')
    .order('created_at', { ascending: true })
    .limit(1)
    .maybeSingle();

  if (earliestError) throw new Error(earliestError.message);

  const earliestPaper = earliestPaperData as Tables<'papers'> | null;

  if (!earliestPaper) {
    return [];
  }

  const earliestDate = new Date(earliestPaper.created_at);
  earliestDate.setHours(0, 0, 0, 0);

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const results: CumulativeDailyItem[] = [];
  let currentDate = new Date(earliestDate);

  // Iterate through each date from earliest to today
  while (currentDate <= today) {
    const dateStr = currentDate.toISOString().split('T')[0];

    // Check if we have a historical snapshot for this date
    if (latestSnapshotDate && currentDate <= latestSnapshotDate) {
      const { data: snapshotData, error: snapError } = await supabase
        .from('paper_status_history')
        .select('*')
        .eq('date', dateStr)
        .maybeSingle();

      if (snapError) throw new Error(snapError.message);

      const snapshot = snapshotData as Tables<'paper_status_history'> | null;

      if (snapshot) {
        // Calculate daily count from previous day's total
        const prevTotal = results.length > 0 ? results[results.length - 1].cumulativeCount : 0;
        const dailyCount = snapshot.total_count - prevTotal;

        results.push({
          date: dateStr,
          dailyCount,
          cumulativeCount: snapshot.total_count,
          cumulativeFailed: snapshot.failed_count,
          cumulativeProcessed: snapshot.processed_count,
          cumulativeNotStarted: snapshot.not_started_count,
          cumulativeProcessing: snapshot.processing_count,
        });

        currentDate.setDate(currentDate.getDate() + 1);
        continue;
      }
    }

    // Use live inference for dates after latest snapshot or without snapshots
    const endOfDay = new Date(currentDate);
    endOfDay.setHours(23, 59, 59, 999);
    const endOfDayStr = endOfDay.toISOString();

    // Count papers created by this date
    const { count: totalCount, error: totalError } = await supabase
      .from('papers')
      .select('*', { count: 'exact', head: true })
      .lte('created_at', endOfDayStr);

    if (totalError) throw new Error(totalError.message);

    // Count by status as of end of day (approximation using current status)
    const [failedResult, processedResult, notStartedResult, processingResult] = await Promise.all([
      supabase
        .from('papers')
        .select('*', { count: 'exact', head: true })
        .lte('created_at', endOfDayStr)
        .eq('status', 'failed')
        .lte('finished_at', endOfDayStr),
      supabase
        .from('papers')
        .select('*', { count: 'exact', head: true })
        .lte('created_at', endOfDayStr)
        .in('status', ['completed', 'partially_completed'])
        .lte('finished_at', endOfDayStr),
      supabase
        .from('papers')
        .select('*', { count: 'exact', head: true })
        .lte('created_at', endOfDayStr)
        .eq('status', 'not_started'),
      supabase
        .from('papers')
        .select('*', { count: 'exact', head: true })
        .lte('created_at', endOfDayStr)
        .eq('status', 'processing'),
    ]);

    if (failedResult.error) throw new Error(failedResult.error.message);
    if (processedResult.error) throw new Error(processedResult.error.message);
    if (notStartedResult.error) throw new Error(notStartedResult.error.message);
    if (processingResult.error) throw new Error(processingResult.error.message);

    const prevTotal = results.length > 0 ? results[results.length - 1].cumulativeCount : 0;
    const dailyCount = (totalCount ?? 0) - prevTotal;

    results.push({
      date: dateStr,
      dailyCount,
      cumulativeCount: totalCount ?? 0,
      cumulativeFailed: failedResult.count ?? 0,
      cumulativeProcessed: processedResult.count ?? 0,
      cumulativeNotStarted: notStartedResult.count ?? 0,
      cumulativeProcessing: processingResult.count ?? 0,
    });

    currentDate.setDate(currentDate.getDate() + 1);
  }

  return results;
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Maps a database paper row to the API Paper interface.
 * @param paper - Database paper row
 * @returns API Paper object
 */
async function mapDbRowToApiPaper(paper: Tables<'papers'>): Promise<Paper> {
  return {
    paperUuid: paper.paper_uuid,
    arxivId: paper.arxiv_id,
    arxivVersion: paper.arxiv_version,
    arxivUrl: paper.arxiv_url,
    title: paper.title,
    authors: paper.authors,
    status: paper.status as PaperStatus,
    errorMessage: paper.error_message,
    initiatedByUserId: paper.initiated_by_user_id,
    createdAt: new Date(paper.created_at),
    updatedAt: new Date(paper.updated_at),
    startedAt: paper.started_at ? new Date(paper.started_at) : null,
    finishedAt: paper.finished_at ? new Date(paper.finished_at) : null,
    numPages: paper.num_pages,
    processingTimeSeconds: paper.processing_time_seconds,
    totalCost: paper.total_cost,
    avgCostPerPage: paper.avg_cost_per_page,
    thumbnailUrl: await getPaperThumbnailUrl(paper.paper_uuid),
    externalPopularitySignals: paper.external_popularity_signals as Record<
      string,
      unknown
    > | null,
    contentHash: paper.content_hash,
    pdfUrl: paper.pdf_url,
  };
}

/**
 * Maps a database paper row to the JobDbStatus interface.
 * @param paper - Database paper row
 * @returns JobDbStatus object
 */
async function mapDbRowToJobDbStatus(paper: Tables<'papers'>): Promise<JobDbStatus> {
  return {
    paperUuid: paper.paper_uuid,
    status: paper.status as PaperStatus,
    errorMessage: paper.error_message,
    createdAt: new Date(paper.created_at),
    updatedAt: new Date(paper.updated_at),
    startedAt: paper.started_at ? new Date(paper.started_at) : null,
    finishedAt: paper.finished_at ? new Date(paper.finished_at) : null,
    arxivId: paper.arxiv_id,
    arxivVersion: paper.arxiv_version,
    arxivUrl: paper.arxiv_url,
    title: paper.title,
    authors: paper.authors,
    numPages: paper.num_pages,
    thumbnailUrl: await getPaperThumbnailUrl(paper.paper_uuid),
    processingTimeSeconds: paper.processing_time_seconds,
    totalCost: paper.total_cost,
    avgCostPerPage: paper.avg_cost_per_page,
  };
}
