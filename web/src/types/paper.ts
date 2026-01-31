/**
 * Paper-related type definitions for the Paper Summarizer application.
 *
 * Responsibilities:
 * - Define paper entity types (full, minimal, summary views)
 * - Define paper processing status types
 * - Define API request/response DTOs for paper endpoints
 *
 * Note: Uses camelCase for all properties (TypeScript convention).
 * The internal database `id` (BigInt) is not exposed; use `paperUuid` for identification.
 */

// ============================================================================
// CONSTANTS / TYPES
// ============================================================================

/**
 * Possible processing states for a paper.
 */
export type PaperStatus = 'not_started' | 'processing' | 'completed' | 'failed';

// ============================================================================
// INTERFACES - Paper Content Types
// ============================================================================

/**
 * Bounding box coordinates as normalized values (0-1).
 * Format: [x1, y1, x2, y2]
 */
export type BoundingBox = [number, number, number, number];

/**
 * A figure extracted from the paper PDF.
 */
export interface Figure {
  /** Unique identifier for the figure within the paper */
  figureIdentifier: string;
  /** Short display ID (e.g., "Fig. 1") */
  shortId?: string;
  /** Page number where the figure appears */
  locationPage: number;
  /** AI-generated explanation of the figure */
  explanation: string;
  /** Base64 data URL of the figure image */
  imageDataUrl: string;
  /** Pages that reference this figure */
  referencedOnPages: number[];
  /** Normalized bounding box coordinates */
  boundingBox: BoundingBox;
}

/**
 * A table extracted from the paper PDF.
 */
export interface Table {
  /** Unique identifier for the table within the paper */
  tableIdentifier: string;
  /** Page number where the table appears */
  locationPage: number;
  /** AI-generated explanation of the table */
  explanation: string;
  /** Base64 data URL of the table image */
  imageDataUrl: string;
  /** Pages that reference this table */
  referencedOnPages: number[];
  /** Normalized bounding box coordinates */
  boundingBox: BoundingBox;
}

/**
 * A section within the paper structure.
 */
export interface Section {
  /** Heading level (1 = top level) */
  level: number;
  /** Section title text */
  sectionTitle: string;
  /** First page of section content */
  startPage: number;
  /** Last page of section content */
  endPage: number;
  /** AI-rewritten content for readability */
  rewrittenContent: string | null;
  /** AI-generated section summary */
  summary: string | null;
  /** Nested subsections */
  subsections: Section[];
}

/**
 * Page metadata (images no longer stored).
 * @deprecated Page images are no longer stored in the database.
 */
export interface Page {
  /** Page number (1-indexed) */
  pageNumber: number;
  /** Base64 data URL of the page image (deprecated) */
  imageDataUrl?: string;
}

/**
 * Usage metrics for AI model calls during processing.
 */
export interface UsageSummary {
  /** Currency for cost values */
  currency: 'USD';
  /** Total cost across all models */
  totalCost: number;
  /** Total prompt tokens used */
  totalPromptTokens: number;
  /** Total completion tokens generated */
  totalCompletionTokens: number;
  /** Total tokens (prompt + completion) */
  totalTokens: number;
  /** Breakdown by model name */
  byModel: Record<string, ModelUsage>;
}

/**
 * Usage metrics for a single AI model.
 */
export interface ModelUsage {
  /** Number of API calls made */
  numCalls: number;
  /** Total cost for this model */
  totalCost: number;
  /** Prompt tokens used */
  promptTokens: number;
  /** Completion tokens generated */
  completionTokens: number;
  /** Total tokens for this model */
  totalTokens: number;
}

// ============================================================================
// INTERFACES - Paper Entity Types
// ============================================================================

/**
 * Full paper record with all database fields.
 * Used for complete paper data in API responses.
 */
export interface Paper {
  /** UUID identifier for the paper */
  paperUuid: string;
  /** arXiv identifier (e.g., "2301.00001") */
  arxivId: string | null;
  /** arXiv version (e.g., "v1") */
  arxivVersion: string | null;
  /** Full arXiv URL */
  arxivUrl: string | null;
  /** Paper title */
  title: string | null;
  /** Comma-separated author names */
  authors: string | null;
  /** Current processing status */
  status: PaperStatus;
  /** Error message if processing failed */
  errorMessage: string | null;
  /** User ID who initiated processing */
  initiatedByUserId: string | null;
  /** When the paper record was created */
  createdAt: Date;
  /** When the paper record was last updated */
  updatedAt: Date;
  /** When processing started */
  startedAt: Date | null;
  /** When processing finished */
  finishedAt: Date | null;
  /** Number of pages in the PDF */
  numPages: number | null;
  /** Total processing time in seconds */
  processingTimeSeconds: number | null;
  /** Total cost of AI processing in USD */
  totalCost: number | null;
  /** Average cost per page in USD */
  avgCostPerPage: number | null;
  /** Base64 data URL of thumbnail image */
  thumbnailDataUrl: string | null;
  /** External popularity metrics (JSON) */
  externalPopularitySignals: Record<string, unknown> | null;
  /** Full processed content as JSON string */
  processedContent: string | null;
  /** Hash of content for deduplication */
  contentHash: string | null;
  /** Direct URL to PDF file */
  pdfUrl: string | null;
}

/**
 * Minimal paper data for list views.
 * Optimized for displaying paper cards.
 */
export interface MinimalPaper {
  /** UUID identifier for the paper */
  paperUuid: string;
  /** Paper title */
  title: string | null;
  /** Comma-separated author names */
  authors: string | null;
  /** Base64 data URL of thumbnail image */
  thumbnailDataUrl: string | null;
  /** URL slug for the paper page */
  slug: string | null;
  /** URL to thumbnail endpoint (constructed from paperUuid) */
  thumbnailUrl: string | null;
}

/**
 * Alias for MinimalPaper for backward compatibility.
 * Used in list views and paper cards.
 */
export type MinimalPaperItem = MinimalPaper;

/**
 * Paper summary for quick display.
 * Used by the summary endpoint.
 */
export interface PaperSummary {
  /** UUID identifier (named paperId for legacy compatibility) */
  paperId: string;
  /** Paper title */
  title: string | null;
  /** Comma-separated author names */
  authors: string | null;
  /** Full arXiv URL */
  arxivUrl: string | null;
  /** AI-generated 5-minute summary */
  fiveMinuteSummary: string | null;
  /** Number of pages in the PDF */
  pageCount: number;
  /** URL to thumbnail image endpoint */
  thumbnailUrl: string | null;
}

/**
 * Processed paper content structure.
 * Returned from the paper JSON endpoint.
 */
export interface ProcessedPaperContent {
  /** UUID identifier */
  paperId: string;
  /** Paper title */
  title: string | null;
  /** Comma-separated author names */
  authors: string | null;
  /** Full arXiv URL */
  arxivUrl: string | null;
  /** Base64 data URL of thumbnail */
  thumbnailDataUrl: string | null;
  /** AI-generated 5-minute summary */
  fiveMinuteSummary: string | null;
  /** Complete markdown content */
  finalMarkdown: string | null;
  /** Structured sections */
  sections: Section[];
  /** Extracted tables */
  tables: Table[];
  /** Extracted figures */
  figures: Figure[];
  /** Page metadata (deprecated) */
  pages: Page[];
  /** AI usage metrics */
  usageSummary?: UsageSummary;
  /** Processing time in seconds */
  processingTimeSeconds: number | null;
}

// ============================================================================
// INTERFACES - Paginated Responses
// ============================================================================

/**
 * Paginated response for minimal paper list.
 */
export interface PaginatedMinimalPapers {
  /** List of papers for current page */
  items: MinimalPaper[];
  /** Total number of papers */
  total: number;
  /** Current page number (1-indexed) */
  page: number;
  /** Items per page */
  limit: number;
  /** Whether more pages exist */
  hasMore: boolean;
}

// ============================================================================
// INTERFACES - Job Status
// ============================================================================

/**
 * Paper processing job status from database.
 * Used for tracking paper processing progress.
 */
export interface JobDbStatus {
  /** UUID identifier for the paper */
  paperUuid: string;
  /** Current processing status */
  status: PaperStatus;
  /** Error message if failed */
  errorMessage: string | null;
  /** When the paper record was created */
  createdAt: Date;
  /** When the paper record was last updated */
  updatedAt: Date;
  /** When processing started */
  startedAt: Date | null;
  /** When processing finished */
  finishedAt: Date | null;
  /** arXiv identifier */
  arxivId: string | null;
  /** arXiv version */
  arxivVersion: string | null;
  /** Full arXiv URL */
  arxivUrl: string | null;
  /** Paper title */
  title: string | null;
  /** Comma-separated author names */
  authors: string | null;
  /** Number of pages in the PDF */
  numPages: number | null;
  /** Base64 data URL of thumbnail */
  thumbnailDataUrl: string | null;
  /** Processing time in seconds */
  processingTimeSeconds: number | null;
  /** Total processing cost in USD */
  totalCost: number | null;
  /** Average cost per page in USD */
  avgCostPerPage: number | null;
}

// ============================================================================
// INTERFACES - API Request/Response DTOs
// ============================================================================

/**
 * Request body for enqueuing an arXiv paper for processing.
 */
export interface EnqueueArxivRequest {
  /** arXiv URL or ID to process */
  url: string;
}

/**
 * Response from enqueuing an arXiv paper.
 */
export interface EnqueueArxivResponse {
  /** Database ID of the created job */
  jobDbId: number;
  /** UUID identifier for the paper */
  paperUuid: string;
  /** Initial status (typically "not_started") */
  status: string;
}

/**
 * Response from checking if an arXiv paper exists and is processed.
 */
export interface CheckArxivResponse {
  /** Whether the paper exists in the database */
  exists: boolean;
  /** URL to the paper viewer page if exists */
  viewerUrl: string | null;
}

/**
 * Response from resolving a paper slug.
 */
export interface ResolveSlugResponse {
  /** UUID of the paper if found */
  paperUuid: string | null;
  /** The slug that was looked up */
  slug: string;
  /** Whether the slug has been marked as deleted */
  tombstone: boolean;
}

/**
 * Processing metrics for a paper.
 * Returns cost and timing information about paper processing.
 */
export interface ProcessingMetrics {
  /** UUID identifier for the paper */
  paperUuid: string;
  /** Current processing status */
  status: PaperStatus;
  /** Number of pages in the PDF */
  numPages: number | null;
  /** Total processing time in seconds */
  processingTimeSeconds: number | null;
  /** Total cost of AI processing in USD */
  totalCost: number | null;
  /** Average cost per page in USD */
  avgCostPerPage: number | null;
  /** When processing started */
  startedAt: Date | null;
  /** When processing finished */
  finishedAt: Date | null;
  /** Error message if processing failed */
  errorMessage: string | null;
}
