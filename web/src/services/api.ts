/**
 * Frontend API Service
 *
 * Client-side service for making API calls to the Next.js API routes.
 *
 * Responsibilities:
 * - Provide typed API functions for paper operations
 * - Provide typed API functions for admin operations
 * - Handle HTTP errors consistently
 *
 * Note: All API calls use relative paths starting with /api/ which route
 * to the Next.js API routes directly (no reverse proxy).
 */

import type { MinimalPaper, PaginatedMinimalPapers } from '../types/paper';

// ============================================================================
// CONSTANTS
// ============================================================================

const API_URL = '/api';

// ============================================================================
// TYPES - API Response DTOs
// ============================================================================

/**
 * Response from enqueuing an arXiv paper for processing.
 */
export type EnqueueArxivResponse = {
  jobDbId: number;
  paperUuid: string;
  status: string;
};

/**
 * Paper processing job status from database.
 * Used for admin paper list display.
 */
export type JobDbStatus = {
  paperUuid: string;
  status: string;
  errorMessage?: string | null;
  createdAt: string;
  updatedAt: string;
  startedAt?: string | null;
  finishedAt?: string | null;
  arxivId: string;
  arxivVersion?: string | null;
  arxivUrl?: string | null;
  title?: string | null;
  authors?: string | null;
  numPages?: number | null;
  thumbnailDataUrl?: string | null;
  processingTimeSeconds?: number | null;
  totalCost?: number | null;
  avgCostPerPage?: number | null;
};

/**
 * Requested paper from admin endpoint.
 */
export type RequestedPaper = {
  arxivId: string;
  arxivAbsUrl: string;
  arxivPdfUrl: string;
  requestCount: number;
  firstRequestedAt: string;
  lastRequestedAt: string;
  title?: string | null;
  authors?: string | null;
  numPages?: number | null;
};

/**
 * Response from checking arXiv paper existence.
 */
export type CheckArxivResponse = {
  exists: boolean;
  viewerUrl?: string | null;
};

/**
 * Author information from arXiv metadata.
 */
export type ArxivAuthor = {
  name: string;
  affiliation?: string | null;
};

/**
 * arXiv paper metadata.
 */
export type ArxivMetadata = {
  arxivId: string;
  latestVersion?: string | null;
  title: string;
  authors: ArxivAuthor[];
  summary: string;
  categories: string[];
  doi?: string | null;
  journalRef?: string | null;
  submittedAt?: string | null;
  updatedAt?: string | null;
};

/**
 * Response from counting papers since a timestamp.
 */
export type CountPapersSinceResponse = {
  count: number;
};

/**
 * Cumulative daily paper statistics for admin overview.
 */
export type CumulativeDailyPaperItem = {
  date: string;
  dailyCount: number;
  cumulativeCount: number;
  cumulativeFailed: number;
  cumulativeProcessed: number;
  cumulativeNotStarted: number;
  cumulativeProcessing: number;
};

/**
 * Paper summary response from the summary endpoint.
 */
export type PaperSummaryResponse = {
  paperId: string;
  title?: string | null;
  authors?: string | null;
  arxivUrl?: string | null;
  fiveMinuteSummary?: string | null;
  pageCount: number;
  thumbnailUrl?: string | null;
};

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Handles HTTP error responses by throwing an error with the response text.
 * @param response - The fetch Response object
 * @throws Error with status and message
 */
async function handleErrorResponse(response: Response): Promise<never> {
  const errorText = await response.text();
  throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
}

// ============================================================================
// PAPER API FUNCTIONS
// ============================================================================

/**
 * Enqueue an arXiv paper for processing.
 * @param url - arXiv URL or ID
 * @returns Enqueue response with paper UUID and status
 */
export async function enqueueArxiv(url: string): Promise<EnqueueArxivResponse> {
  const response = await fetch(`${API_URL}/papers/enqueue_arxiv`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  if (!response.ok) {
    await handleErrorResponse(response);
  }
  return response.json();
}

/**
 * List all papers from the admin endpoint.
 * @param status - Optional status filter
 * @returns List of papers with job status
 */
export async function listPapers(status?: string): Promise<JobDbStatus[]> {
  const url = new URL(`${API_URL}/admin/papers`, window.location.origin);
  if (status) url.searchParams.set('status', status);
  const response = await fetch(url.toString());
  if (!response.ok) {
    await handleErrorResponse(response);
  }
  return response.json();
}

/**
 * List all requested papers from the admin endpoint.
 * @returns List of requested papers with metadata
 */
export async function listRequestedPapers(): Promise<RequestedPaper[]> {
  const response = await fetch(`${API_URL}/admin/requested_papers`);
  if (!response.ok) {
    await handleErrorResponse(response);
  }
  return response.json();
}

/**
 * Start processing a requested paper.
 * @param arxivIdOrUrl - arXiv ID or URL
 * @returns Paper UUID and status
 */
export async function startProcessingRequested(
  arxivIdOrUrl: string
): Promise<{ paperUuid: string; status: string }> {
  const encoded = encodeURIComponent(arxivIdOrUrl);
  const response = await fetch(
    `${API_URL}/admin/requested_papers/${encoded}/start_processing`,
    { method: 'POST' }
  );
  if (!response.ok) {
    await handleErrorResponse(response);
  }
  return response.json();
}

/**
 * Delete a requested paper.
 * @param arxivIdOrUrl - arXiv ID or URL
 * @returns Deletion confirmation
 */
export async function deleteRequestedPaper(
  arxivIdOrUrl: string
): Promise<{ deleted: string }> {
  const encoded = encodeURIComponent(arxivIdOrUrl);
  const response = await fetch(`${API_URL}/admin/requested_papers/${encoded}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    await handleErrorResponse(response);
  }
  return response.json();
}

/**
 * List minimal papers (not paginated).
 * @returns List of minimal paper items
 */
export async function listMinimalPapers(): Promise<MinimalPaper[]> {
  const response = await fetch(`${API_URL}/papers/minimal`);
  if (!response.ok) {
    await handleErrorResponse(response);
  }
  return response.json();
}

/**
 * List minimal papers with pagination.
 * @param page - Page number (1-indexed)
 * @param limit - Items per page
 * @returns Paginated response with papers
 */
export async function listMinimalPapersPaginated(
  page: number,
  limit: number
): Promise<PaginatedMinimalPapers> {
  const url = new URL(`${API_URL}/papers/minimal`, window.location.origin);
  url.searchParams.set('page', page.toString());
  url.searchParams.set('limit', limit.toString());
  const response = await fetch(url.toString());
  if (!response.ok) {
    await handleErrorResponse(response);
  }
  return response.json();
}

/**
 * Count papers created since a timestamp.
 * @param since - ISO timestamp string
 * @returns Count of papers
 */
export async function countPapersSince(since: string): Promise<CountPapersSinceResponse> {
  const url = new URL(`${API_URL}/papers/count_since`, window.location.origin);
  url.searchParams.set('since', since);
  const response = await fetch(url.toString());
  if (!response.ok) {
    await handleErrorResponse(response);
  }
  return response.json();
}

/**
 * Fetch the full markdown content for a paper.
 * @param paperUuid - Paper UUID
 * @returns Final markdown string
 */
export async function fetchPaperMarkdown(paperUuid: string): Promise<string> {
  const response = await fetch(`${API_URL}/papers/${paperUuid}/markdown`);
  if (!response.ok) {
    await handleErrorResponse(response);
  }
  const data = await response.json();
  return data.finalMarkdown;
}

/**
 * Fetch the summary for a paper.
 * @param paperUuid - Paper UUID
 * @returns Paper summary response
 */
export async function fetchPaperSummary(paperUuid: string): Promise<PaperSummaryResponse> {
  const response = await fetch(`${API_URL}/papers/${paperUuid}/summary`);
  if (!response.ok) {
    await handleErrorResponse(response);
  }
  return response.json();
}

/**
 * Check if an arXiv paper exists and is processed.
 * @param arxivIdOrUrl - arXiv ID or URL (raw, not pre-encoded)
 * @returns Check response with exists flag and viewer URL
 */
export async function checkArxiv(arxivIdOrUrl: string): Promise<CheckArxivResponse> {
  // Reject pre-encoded inputs to avoid double-encoding issues
  if (/%[0-9A-Fa-f]{2}/.test(arxivIdOrUrl)) {
    throw new Error('checkArxiv received an already-encoded value; pass a raw arXiv id or URL');
  }
  const encoded = encodeURIComponent(arxivIdOrUrl);
  const response = await fetch(`${API_URL}/papers/check_arxiv/${encoded}`);
  if (!response.ok) {
    await handleErrorResponse(response);
  }
  return response.json();
}

/**
 * Fetch arXiv metadata for a paper.
 * @param arxivIdOrUrl - arXiv ID or URL
 * @returns arXiv metadata
 */
export async function getArxivMetadata(arxivIdOrUrl: string): Promise<ArxivMetadata> {
  const encoded = encodeURIComponent(arxivIdOrUrl);
  const response = await fetch(`${API_URL}/arxiv-metadata/${encoded}`);
  if (!response.ok) {
    await handleErrorResponse(response);
  }
  return response.json();
}

/**
 * Get cumulative daily paper statistics.
 * @returns List of daily statistics
 */
export async function getCumulativeDailyPapers(): Promise<CumulativeDailyPaperItem[]> {
  const response = await fetch(`${API_URL}/admin/papers/cumulative_daily`);
  if (!response.ok) {
    await handleErrorResponse(response);
  }
  return response.json();
}
