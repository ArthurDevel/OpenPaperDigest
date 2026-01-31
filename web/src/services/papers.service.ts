/**
 * Paper Service
 *
 * Provides business logic for paper-related operations.
 * - CRUD operations for papers (list, get by uuid/slug, summary, content)
 * - arXiv paper checking and enqueuing
 * - Thumbnail retrieval and base64 decoding
 * - Paper JSON import functionality
 */

import { prisma } from '@/lib/db';
import { normalizeId } from '@/lib/arxiv';
import * as slugsService from '@/services/slugs.service';
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
  const skip = (page - 1) * limit;

  // Only fetch completed papers with their slugs
  const [papers, total] = await Promise.all([
    prisma.paper.findMany({
      where: { status: 'completed' },
      select: {
        paperUuid: true,
        title: true,
        authors: true,
        thumbnailDataUrl: true,
        slugs: {
          where: { tombstone: false },
          orderBy: { createdAt: 'desc' },
          take: 1,
          select: { slug: true },
        },
      },
      orderBy: { finishedAt: 'desc' },
      skip,
      take: limit,
    }),
    prisma.paper.count({ where: { status: 'completed' } }),
  ]);

  const items: MinimalPaper[] = papers.map((paper) => ({
    paperUuid: paper.paperUuid,
    title: paper.title,
    authors: paper.authors,
    thumbnailDataUrl: paper.thumbnailDataUrl,
    slug: paper.slugs[0]?.slug ?? null,
    thumbnailUrl: `/api/papers/thumbnails/${paper.paperUuid}`,
  }));

  return {
    items,
    total,
    page,
    limit,
    hasMore: skip + papers.length < total,
  };
}

/**
 * Get a full paper record by UUID.
 * @param uuid - The paper UUID
 * @returns Full paper record or null if not found
 */
export async function getPaperByUuid(uuid: string): Promise<Paper | null> {
  const paper = await prisma.paper.findUnique({
    where: { paperUuid: uuid },
  });

  if (!paper) {
    return null;
  }

  return mapPrismaToApiPaper(paper);
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
  const paper = await prisma.paper.findUnique({
    where: { paperUuid: uuid },
    select: {
      paperUuid: true,
      title: true,
      authors: true,
      arxivUrl: true,
      processedContent: true,
      numPages: true,
    },
  });

  if (!paper) {
    throw new Error(`Paper not found: ${uuid}`);
  }

  // Extract five_minute_summary from processed content
  let fiveMinuteSummary: string | null = null;
  if (paper.processedContent) {
    try {
      const content = JSON.parse(paper.processedContent);
      fiveMinuteSummary = content.five_minute_summary ?? null;
    } catch {
      // Ignore parse errors
    }
  }

  return {
    paperId: paper.paperUuid,
    title: paper.title,
    authors: paper.authors,
    arxivUrl: paper.arxivUrl,
    fiveMinuteSummary,
    pageCount: paper.numPages ?? 0,
    thumbnailUrl: `/api/papers/thumbnails/${paper.paperUuid}`,
  };
}

/**
 * Get the raw markdown content for a paper.
 * @param uuid - The paper UUID
 * @returns Markdown string or throws if not found
 */
export async function getPaperMarkdown(uuid: string): Promise<string> {
  const paper = await prisma.paper.findUnique({
    where: { paperUuid: uuid },
    select: { processedContent: true },
  });

  if (!paper) {
    throw new Error(`Paper not found: ${uuid}`);
  }

  if (!paper.processedContent) {
    throw new Error(`Paper has no processed content: ${uuid}`);
  }

  try {
    const content = JSON.parse(paper.processedContent);
    return content.final_markdown ?? '';
  } catch {
    throw new Error(`Failed to parse processed content for paper: ${uuid}`);
  }
}

/**
 * Get the full processed content JSON for a paper.
 * @param uuid - The paper UUID
 * @returns Parsed JSON object or throws if not found
 */
export async function getPaperJson(uuid: string): Promise<Record<string, unknown>> {
  const paper = await prisma.paper.findUnique({
    where: { paperUuid: uuid },
    select: {
      paperUuid: true,
      title: true,
      authors: true,
      arxivUrl: true,
      thumbnailDataUrl: true,
      processedContent: true,
      processingTimeSeconds: true,
    },
  });

  if (!paper) {
    throw new Error(`Paper not found: ${uuid}`);
  }

  // Parse the processed content if available
  let parsedContent: Record<string, unknown> = {};
  if (paper.processedContent) {
    try {
      parsedContent = JSON.parse(paper.processedContent);
    } catch {
      throw new Error(`Failed to parse processed content for paper: ${uuid}`);
    }
  }

  // Return combined data with paper metadata
  return {
    paperId: paper.paperUuid,
    title: paper.title,
    authors: paper.authors,
    arxivUrl: paper.arxivUrl,
    thumbnailDataUrl: paper.thumbnailDataUrl,
    processingTimeSeconds: paper.processingTimeSeconds,
    ...parsedContent,
  };
}

/**
 * Count completed papers since a given timestamp.
 * @param since - Timestamp to count from
 * @returns Number of completed papers since the timestamp
 */
export async function countPapersSince(since: Date): Promise<number> {
  return prisma.paper.count({
    where: {
      status: 'completed',
      finishedAt: { gte: since },
    },
  });
}

/**
 * Check if an arXiv paper exists and is processed.
 * @param arxivIdOrUrl - arXiv ID or URL to check
 * @returns Object with exists flag and viewer URL if found
 */
export async function checkArxivExists(arxivIdOrUrl: string): Promise<CheckArxivResponse> {
  // Normalize the arXiv ID
  const { arxivId } = normalizeId(arxivIdOrUrl);

  // Look up paper by arXiv ID
  const paper = await prisma.paper.findUnique({
    where: { arxivId },
    select: {
      paperUuid: true,
      status: true,
      slugs: {
        where: { tombstone: false },
        orderBy: { createdAt: 'desc' },
        take: 1,
        select: { slug: true },
      },
    },
  });

  if (!paper || paper.status !== 'completed') {
    return { exists: false, viewerUrl: null };
  }

  // Build viewer URL using slug if available, otherwise UUID
  const slug = paper.slugs[0]?.slug;
  const viewerUrl = slug ? `${BASE_VIEWER_URL}/${slug}` : `${BASE_VIEWER_URL}/${paper.paperUuid}`;

  return { exists: true, viewerUrl };
}

/**
 * Create a paper record for arXiv processing.
 * @param url - arXiv URL or ID to enqueue
 * @returns Created job information
 */
export async function enqueueArxiv(url: string): Promise<EnqueueArxivResponse> {
  // Normalize and validate the arXiv ID
  const { arxivId, version } = normalizeId(url);

  // Check if paper already exists
  const existing = await prisma.paper.findUnique({
    where: { arxivId },
    select: { id: true, paperUuid: true, status: true },
  });

  if (existing) {
    return {
      jobDbId: Number(existing.id),
      paperUuid: existing.paperUuid,
      status: existing.status,
    };
  }

  // Create new paper record
  const paperUuid = randomUUID();
  const paper = await prisma.paper.create({
    data: {
      paperUuid,
      arxivId,
      arxivVersion: version,
      arxivUrl: `https://arxiv.org/abs/${arxivId}${version ?? ''}`,
      status: 'not_started',
    },
  });

  return {
    jobDbId: Number(paper.id),
    paperUuid: paper.paperUuid,
    status: paper.status,
  };
}

/**
 * Get thumbnail image bytes from a paper's base64 data URL.
 * @param uuid - The paper UUID
 * @returns Buffer and media type for the thumbnail
 */
export async function getThumbnail(
  uuid: string
): Promise<{ data: Buffer; mediaType: string }> {
  const paper = await prisma.paper.findUnique({
    where: { paperUuid: uuid },
    select: { thumbnailDataUrl: true },
  });

  if (!paper) {
    throw new Error(`Paper not found: ${uuid}`);
  }

  if (!paper.thumbnailDataUrl) {
    throw new Error(`Paper has no thumbnail: ${uuid}`);
  }

  // Parse the data URL format: data:image/png;base64,<data>
  const dataUrlMatch = /^data:([^;]+);base64,(.+)$/.exec(paper.thumbnailDataUrl);
  if (!dataUrlMatch) {
    throw new Error(`Invalid thumbnail data URL format for paper: ${uuid}`);
  }

  const mediaType = dataUrlMatch[1];
  const base64Data = dataUrlMatch[2];
  const data = Buffer.from(base64Data, 'base64');

  return { data, mediaType };
}

/**
 * Import a paper JSON and write it to the paperjsons directory.
 * Creates or updates the paper record in the database.
 * @param paper - Paper JSON object with paper_uuid and other fields
 * @returns Job status information
 */
export async function importPaperJson(
  paper: Record<string, unknown>
): Promise<JobDbStatus> {
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

  // Upsert paper record
  const now = new Date();
  const upsertData = {
    arxivId: (paper.arxiv_id as string) ?? null,
    arxivVersion: (paper.arxiv_version as string) ?? null,
    arxivUrl: (paper.arxiv_url as string) ?? null,
    title: (paper.title as string) ?? null,
    authors: (paper.authors as string) ?? null,
    status: 'completed' as const,
    numPages: (paper.num_pages as number) ?? null,
    thumbnailDataUrl: (paper.thumbnail_data_url as string) ?? null,
    processedContent: paper.processed_content
      ? JSON.stringify(paper.processed_content)
      : null,
    finishedAt: now,
    updatedAt: now,
  };

  const dbPaper = await prisma.paper.upsert({
    where: { paperUuid },
    create: {
      paperUuid,
      createdAt: now,
      ...upsertData,
    },
    update: upsertData,
  });

  return mapPrismaToJobDbStatus(dbPaper);
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
  // Parse status filter if provided
  const statuses = statusFilter
    ? statusFilter.split(',').map((s) => s.trim()).filter(Boolean)
    : null;

  const papers = await prisma.paper.findMany({
    where: statuses ? { status: { in: statuses } } : undefined,
    select: {
      paperUuid: true,
      status: true,
      errorMessage: true,
      createdAt: true,
      updatedAt: true,
      startedAt: true,
      finishedAt: true,
      arxivId: true,
      arxivVersion: true,
      arxivUrl: true,
      title: true,
      authors: true,
      numPages: true,
      processingTimeSeconds: true,
      totalCost: true,
      avgCostPerPage: true,
      // Note: thumbnailDataUrl excluded for performance in admin list
    },
    orderBy: { createdAt: 'desc' },
    take: limit,
  });

  return papers.map((paper) => ({
    paperUuid: paper.paperUuid,
    status: paper.status as PaperStatus,
    errorMessage: paper.errorMessage,
    createdAt: paper.createdAt,
    updatedAt: paper.updatedAt,
    startedAt: paper.startedAt,
    finishedAt: paper.finishedAt,
    arxivId: paper.arxivId,
    arxivVersion: paper.arxivVersion,
    arxivUrl: paper.arxivUrl,
    title: paper.title,
    authors: paper.authors,
    numPages: paper.numPages,
    thumbnailDataUrl: null, // Not included in admin list for performance
    processingTimeSeconds: paper.processingTimeSeconds,
    totalCost: paper.totalCost,
    avgCostPerPage: paper.avgCostPerPage,
  }));
}

/**
 * Delete a paper by UUID.
 * Removes the paper record and associated slugs from the database.
 * @param uuid - The paper UUID to delete
 * @returns True if paper was deleted, false if not found
 */
export async function deletePaper(uuid: string): Promise<boolean> {
  const paper = await prisma.paper.findUnique({
    where: { paperUuid: uuid },
    select: { id: true },
  });

  if (!paper) {
    return false;
  }

  // Delete associated slugs first (foreign key constraint)
  await prisma.paperSlug.deleteMany({
    where: { paperUuid: uuid },
  });

  // Delete the paper
  await prisma.paper.delete({
    where: { paperUuid: uuid },
  });

  return true;
}

/**
 * Restart paper processing by resetting its status.
 * Sets status to 'not_started' and clears error/timing fields.
 * @param uuid - The paper UUID to restart
 * @returns Updated job status or throws if paper not found or already processing
 */
export async function restartPaper(uuid: string): Promise<JobDbStatus> {
  const paper = await prisma.paper.findUnique({
    where: { paperUuid: uuid },
    select: {
      id: true,
      status: true,
    },
  });

  if (!paper) {
    throw new Error(`Paper not found: ${uuid}`);
  }

  if (paper.status === 'processing') {
    throw new Error('Paper is already processing');
  }

  // Reset paper for reprocessing
  const updated = await prisma.paper.update({
    where: { paperUuid: uuid },
    data: {
      status: 'not_started',
      errorMessage: null,
      startedAt: null,
      finishedAt: null,
      updatedAt: new Date(),
    },
    select: {
      paperUuid: true,
      status: true,
      errorMessage: true,
      createdAt: true,
      updatedAt: true,
      startedAt: true,
      finishedAt: true,
      arxivId: true,
      arxivVersion: true,
      arxivUrl: true,
      title: true,
      authors: true,
      numPages: true,
      thumbnailDataUrl: true,
      processingTimeSeconds: true,
      totalCost: true,
      avgCostPerPage: true,
    },
  });

  return {
    paperUuid: updated.paperUuid,
    status: updated.status as PaperStatus,
    errorMessage: updated.errorMessage,
    createdAt: updated.createdAt,
    updatedAt: updated.updatedAt,
    startedAt: updated.startedAt,
    finishedAt: updated.finishedAt,
    arxivId: updated.arxivId,
    arxivVersion: updated.arxivVersion,
    arxivUrl: updated.arxivUrl,
    title: updated.title,
    authors: updated.authors,
    numPages: updated.numPages,
    thumbnailDataUrl: updated.thumbnailDataUrl,
    processingTimeSeconds: updated.processingTimeSeconds,
    totalCost: updated.totalCost,
    avgCostPerPage: updated.avgCostPerPage,
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
  const paper = await prisma.paper.findUnique({
    where: { paperUuid: uuid },
    select: {
      paperUuid: true,
      status: true,
      numPages: true,
      processingTimeSeconds: true,
      totalCost: true,
      avgCostPerPage: true,
      startedAt: true,
      finishedAt: true,
      errorMessage: true,
    },
  });

  if (!paper) {
    throw new Error(`Paper not found: ${uuid}`);
  }

  return {
    paperUuid: paper.paperUuid,
    status: paper.status as PaperStatus,
    numPages: paper.numPages,
    processingTimeSeconds: paper.processingTimeSeconds,
    totalCost: paper.totalCost,
    avgCostPerPage: paper.avgCostPerPage,
    startedAt: paper.startedAt,
    finishedAt: paper.finishedAt,
    errorMessage: paper.errorMessage,
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
  // Check if there are any papers
  const paperCount = await prisma.paper.count();
  if (paperCount === 0) {
    return [];
  }

  // Get latest snapshot date from history table
  const latestSnapshot = await prisma.paperStatusHistory.findFirst({
    orderBy: { date: 'desc' },
    select: { date: true },
  });
  const latestSnapshotDate = latestSnapshot?.date ?? null;

  // Get earliest paper creation date
  const earliestPaper = await prisma.paper.findFirst({
    orderBy: { createdAt: 'asc' },
    select: { createdAt: true },
  });
  if (!earliestPaper) {
    return [];
  }

  const earliestDate = new Date(earliestPaper.createdAt);
  earliestDate.setHours(0, 0, 0, 0);

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const results: CumulativeDailyItem[] = [];
  let currentDate = new Date(earliestDate);

  // Iterate through each date from earliest to today
  while (currentDate <= today) {
    const dateStr = currentDate.toISOString().split('T')[0];
    const currentDateOnly = new Date(currentDate);

    // Check if we have a historical snapshot for this date
    if (latestSnapshotDate && currentDate <= latestSnapshotDate) {
      const snapshot = await prisma.paperStatusHistory.findUnique({
        where: { date: currentDateOnly },
      });

      if (snapshot) {
        // Calculate daily count from previous day's total
        const prevTotal = results.length > 0 ? results[results.length - 1].cumulativeCount : 0;
        const dailyCount = snapshot.totalCount - prevTotal;

        results.push({
          date: dateStr,
          dailyCount,
          cumulativeCount: snapshot.totalCount,
          cumulativeFailed: snapshot.failedCount,
          cumulativeProcessed: snapshot.processedCount,
          cumulativeNotStarted: snapshot.notStartedCount,
          cumulativeProcessing: snapshot.processingCount,
        });

        currentDate.setDate(currentDate.getDate() + 1);
        continue;
      }
    }

    // Use live inference for dates after latest snapshot or without snapshots
    const endOfDay = new Date(currentDate);
    endOfDay.setHours(23, 59, 59, 999);

    // Count papers created by this date
    const totalCount = await prisma.paper.count({
      where: { createdAt: { lte: endOfDay } },
    });

    // Count by status as of end of day (approximation using current status)
    const [failedCount, processedCount, notStartedCount, processingCount] = await Promise.all([
      prisma.paper.count({
        where: {
          createdAt: { lte: endOfDay },
          status: 'failed',
          finishedAt: { lte: endOfDay },
        },
      }),
      prisma.paper.count({
        where: {
          createdAt: { lte: endOfDay },
          status: 'completed',
          finishedAt: { lte: endOfDay },
        },
      }),
      prisma.paper.count({
        where: {
          createdAt: { lte: endOfDay },
          status: 'not_started',
        },
      }),
      prisma.paper.count({
        where: {
          createdAt: { lte: endOfDay },
          status: 'processing',
        },
      }),
    ]);

    const prevTotal = results.length > 0 ? results[results.length - 1].cumulativeCount : 0;
    const dailyCount = totalCount - prevTotal;

    results.push({
      date: dateStr,
      dailyCount,
      cumulativeCount: totalCount,
      cumulativeFailed: failedCount,
      cumulativeProcessed: processedCount,
      cumulativeNotStarted: notStartedCount,
      cumulativeProcessing: processingCount,
    });

    currentDate.setDate(currentDate.getDate() + 1);
  }

  return results;
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Maps a Prisma Paper record to the API Paper interface.
 * @param paper - Prisma paper record
 * @returns API Paper object
 */
function mapPrismaToApiPaper(
  paper: Awaited<ReturnType<typeof prisma.paper.findUnique>> & object
): Paper {
  return {
    paperUuid: paper.paperUuid,
    arxivId: paper.arxivId,
    arxivVersion: paper.arxivVersion,
    arxivUrl: paper.arxivUrl,
    title: paper.title,
    authors: paper.authors,
    status: paper.status as PaperStatus,
    errorMessage: paper.errorMessage,
    initiatedByUserId: paper.initiatedByUserId,
    createdAt: paper.createdAt,
    updatedAt: paper.updatedAt,
    startedAt: paper.startedAt,
    finishedAt: paper.finishedAt,
    numPages: paper.numPages,
    processingTimeSeconds: paper.processingTimeSeconds,
    totalCost: paper.totalCost,
    avgCostPerPage: paper.avgCostPerPage,
    thumbnailDataUrl: paper.thumbnailDataUrl,
    externalPopularitySignals: paper.externalPopularitySignals as Record<
      string,
      unknown
    > | null,
    processedContent: paper.processedContent,
    contentHash: paper.contentHash,
    pdfUrl: paper.pdfUrl,
  };
}

/**
 * Maps a Prisma Paper record to the JobDbStatus interface.
 * @param paper - Prisma paper record
 * @returns JobDbStatus object
 */
function mapPrismaToJobDbStatus(
  paper: Awaited<ReturnType<typeof prisma.paper.findUnique>> & object
): JobDbStatus {
  return {
    paperUuid: paper.paperUuid,
    status: paper.status as PaperStatus,
    errorMessage: paper.errorMessage,
    createdAt: paper.createdAt,
    updatedAt: paper.updatedAt,
    startedAt: paper.startedAt,
    finishedAt: paper.finishedAt,
    arxivId: paper.arxivId,
    arxivVersion: paper.arxivVersion,
    arxivUrl: paper.arxivUrl,
    title: paper.title,
    authors: paper.authors,
    numPages: paper.numPages,
    thumbnailDataUrl: paper.thumbnailDataUrl,
    processingTimeSeconds: paper.processingTimeSeconds,
    totalCost: paper.totalCost,
    avgCostPerPage: paper.avgCostPerPage,
  };
}
