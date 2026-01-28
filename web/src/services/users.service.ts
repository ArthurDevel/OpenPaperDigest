/**
 * User Service
 *
 * Provides business logic for user-related operations.
 * - User sync from BetterAuth authentication hooks
 * - User list management (add, remove, check papers)
 * - User request management (paper processing requests)
 */

import { prisma } from '@/lib/db';
import type {
  User,
  SyncUserPayload,
  CreatedResponse,
  DeletedResponse,
  ExistsResponse,
  UserListItem,
  UserRequestItem,
  AdminRequestItem,
  AggregatedRequestItem,
  StartProcessingResponse,
} from '@/types/user';
import type { ProcessingMetrics, PaperStatus } from '@/types/paper';

// ============================================================================
// MAIN HANDLERS - User Management
// ============================================================================

/**
 * Create or update a user record from BetterAuth hook data.
 * This is called when a user signs up or logs in for the first time.
 * @param payload - User data from BetterAuth
 * @returns Object indicating whether a new user was created
 */
export async function syncNewUser(payload: SyncUserPayload): Promise<{ created: boolean }> {
  const existing = await prisma.user.findUnique({
    where: { id: payload.id },
  });

  if (existing) {
    return { created: false };
  }

  await prisma.user.create({
    data: {
      id: payload.id,
      email: payload.email,
    },
  });

  return { created: true };
}

/**
 * Get a user record by their auth provider ID.
 * @param authProviderId - The user's ID from BetterAuth
 * @returns User record or null if not found
 */
export async function getUserByAuthProviderId(authProviderId: string): Promise<User | null> {
  const user = await prisma.user.findUnique({
    where: { id: authProviderId },
  });

  if (!user) {
    return null;
  }

  return {
    id: user.id,
    email: user.email,
    createdAt: user.createdAt,
  };
}

// ============================================================================
// MAIN HANDLERS - User List Management
// ============================================================================

/**
 * Add a paper to a user's saved list.
 * @param authProviderId - The user's auth provider ID
 * @param paperUuid - The paper UUID to add
 * @returns Object indicating whether the item was created (false if already existed)
 */
export async function addToList(
  authProviderId: string,
  paperUuid: string
): Promise<CreatedResponse> {
  // Verify user exists
  const user = await prisma.user.findUnique({
    where: { id: authProviderId },
  });
  if (!user) {
    throw new Error(`User not found: ${authProviderId}`);
  }

  // Verify paper exists and get its internal ID
  const paper = await prisma.paper.findUnique({
    where: { paperUuid },
    select: { id: true },
  });
  if (!paper) {
    throw new Error(`Paper not found: ${paperUuid}`);
  }

  // Check if already in list
  const existing = await prisma.userList.findUnique({
    where: {
      userId_paperId: {
        userId: authProviderId,
        paperId: paper.id,
      },
    },
  });

  if (existing) {
    return { created: false };
  }

  await prisma.userList.create({
    data: {
      userId: authProviderId,
      paperId: paper.id,
    },
  });

  return { created: true };
}

/**
 * Remove a paper from a user's saved list.
 * @param authProviderId - The user's auth provider ID
 * @param paperUuid - The paper UUID to remove
 * @returns Object indicating whether the item was deleted (false if didn't exist)
 */
export async function removeFromList(
  authProviderId: string,
  paperUuid: string
): Promise<DeletedResponse> {
  // Get paper internal ID
  const paper = await prisma.paper.findUnique({
    where: { paperUuid },
    select: { id: true },
  });
  if (!paper) {
    return { deleted: false };
  }

  // Try to delete the list entry
  const deleted = await prisma.userList.deleteMany({
    where: {
      userId: authProviderId,
      paperId: paper.id,
    },
  });

  return { deleted: deleted.count > 0 };
}

/**
 * Get all papers in a user's saved list.
 * @param authProviderId - The user's auth provider ID
 * @returns Array of papers in the user's list with metadata
 */
export async function getList(authProviderId: string): Promise<UserListItem[]> {
  const listItems = await prisma.userList.findMany({
    where: { userId: authProviderId },
    include: {
      paper: {
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
      },
    },
    orderBy: { createdAt: 'desc' },
  });

  return listItems.map((item) => ({
    paperUuid: item.paper.paperUuid,
    title: item.paper.title,
    authors: item.paper.authors,
    thumbnailDataUrl: item.paper.thumbnailDataUrl,
    slug: item.paper.slugs[0]?.slug ?? null,
    createdAt: item.createdAt,
  }));
}

/**
 * Check if a paper is in a user's saved list.
 * @param authProviderId - The user's auth provider ID
 * @param paperUuid - The paper UUID to check
 * @returns Object with exists flag
 */
export async function isInList(
  authProviderId: string,
  paperUuid: string
): Promise<ExistsResponse> {
  // Get paper internal ID
  const paper = await prisma.paper.findUnique({
    where: { paperUuid },
    select: { id: true },
  });
  if (!paper) {
    return { exists: false };
  }

  const existing = await prisma.userList.findUnique({
    where: {
      userId_paperId: {
        userId: authProviderId,
        paperId: paper.id,
      },
    },
  });

  return { exists: !!existing };
}

// ============================================================================
// MAIN HANDLERS - User Request Management
// ============================================================================

/**
 * Add a paper request for a user.
 * @param authProviderId - The user's auth provider ID
 * @param arxivId - The arXiv ID of the requested paper
 * @param title - The paper title (from arXiv metadata)
 * @param authors - The paper authors (from arXiv metadata)
 * @returns Object indicating whether the request was created (false if already existed)
 */
export async function addRequest(
  authProviderId: string,
  arxivId: string,
  title: string | null,
  authors: string | null
): Promise<CreatedResponse> {
  // Verify user exists
  const user = await prisma.user.findUnique({
    where: { id: authProviderId },
  });
  if (!user) {
    throw new Error(`User not found: ${authProviderId}`);
  }

  // Check if request already exists
  const existing = await prisma.userRequest.findUnique({
    where: {
      userId_arxivId: {
        userId: authProviderId,
        arxivId,
      },
    },
  });

  if (existing) {
    return { created: false };
  }

  await prisma.userRequest.create({
    data: {
      userId: authProviderId,
      arxivId,
      title,
      authors,
    },
  });

  return { created: true };
}

/**
 * Remove a paper request for a user.
 * @param authProviderId - The user's auth provider ID
 * @param arxivId - The arXiv ID to remove
 * @returns Object indicating whether the request was deleted (false if didn't exist)
 */
export async function removeRequest(
  authProviderId: string,
  arxivId: string
): Promise<DeletedResponse> {
  const deleted = await prisma.userRequest.deleteMany({
    where: {
      userId: authProviderId,
      arxivId,
    },
  });

  return { deleted: deleted.count > 0 };
}

/**
 * Get all paper requests for a user.
 * @param authProviderId - The user's auth provider ID
 * @returns Array of user's paper requests with metadata
 */
export async function listRequests(authProviderId: string): Promise<UserRequestItem[]> {
  const requests = await prisma.userRequest.findMany({
    where: { userId: authProviderId },
    orderBy: { createdAt: 'desc' },
  });

  return requests.map((request) => ({
    arxivId: request.arxivId,
    title: request.title,
    authors: request.authors,
    createdAt: request.createdAt,
    isProcessed: request.isProcessed,
    processedSlug: request.processedSlug,
  }));
}

/**
 * Check if a paper request exists for a user.
 * @param authProviderId - The user's auth provider ID
 * @param arxivId - The arXiv ID to check
 * @returns Object with exists flag
 */
export async function doesRequestExist(
  authProviderId: string,
  arxivId: string
): Promise<ExistsResponse> {
  const existing = await prisma.userRequest.findUnique({
    where: {
      userId_arxivId: {
        userId: authProviderId,
        arxivId,
      },
    },
  });

  return { exists: !!existing };
}

/**
 * Get all paper requests from all users (admin only).
 * Returns requests with user email for admin display.
 * @returns Array of all paper requests with user email
 */
export async function getAllRequests(): Promise<AdminRequestItem[]> {
  const requests = await prisma.userRequest.findMany({
    include: {
      user: {
        select: { email: true },
      },
    },
    orderBy: { createdAt: 'desc' },
  });

  return requests.map((request) => ({
    id: Number(request.id),
    userId: request.userId,
    userEmail: request.user.email,
    arxivId: request.arxivId,
    title: request.title,
    authors: request.authors,
    createdAt: request.createdAt,
    isProcessed: request.isProcessed,
    processedSlug: request.processedSlug,
  }));
}

// ============================================================================
// ADMIN HANDLERS - Request Management
// ============================================================================

/**
 * Get aggregated paper requests for admin display.
 * Groups requests by arXiv ID and returns counts.
 * @param limit - Maximum number of items to return
 * @param offset - Number of items to skip for pagination
 * @returns Array of aggregated request items
 */
export async function getAggregatedRequests(
  limit: number = 500,
  offset: number = 0
): Promise<AggregatedRequestItem[]> {
  // Get all requests grouped by arxivId
  const requests = await prisma.userRequest.findMany({
    orderBy: { createdAt: 'desc' },
  });

  // Group by arxivId
  const grouped = new Map<string, {
    arxivId: string;
    requests: typeof requests;
    title: string | null;
    authors: string | null;
    isProcessed: boolean;
    processedSlug: string | null;
  }>();

  for (const req of requests) {
    const existing = grouped.get(req.arxivId);
    if (existing) {
      existing.requests.push(req);
      // Update title/authors if not set
      if (!existing.title && req.title) existing.title = req.title;
      if (!existing.authors && req.authors) existing.authors = req.authors;
      // Mark as processed if any request is processed
      if (req.isProcessed) {
        existing.isProcessed = true;
        existing.processedSlug = req.processedSlug;
      }
    } else {
      grouped.set(req.arxivId, {
        arxivId: req.arxivId,
        requests: [req],
        title: req.title,
        authors: req.authors,
        isProcessed: req.isProcessed,
        processedSlug: req.processedSlug,
      });
    }
  }

  // Convert to array and calculate aggregates
  const items: AggregatedRequestItem[] = [];
  for (const [arxivId, data] of grouped) {
    const sortedRequests = data.requests.sort(
      (a, b) => a.createdAt.getTime() - b.createdAt.getTime()
    );
    items.push({
      arxivId,
      arxivAbsUrl: `https://arxiv.org/abs/${arxivId}`,
      arxivPdfUrl: `https://arxiv.org/pdf/${arxivId}.pdf`,
      requestCount: data.requests.length,
      firstRequestedAt: sortedRequests[0].createdAt,
      lastRequestedAt: sortedRequests[sortedRequests.length - 1].createdAt,
      title: data.title,
      authors: data.authors,
      numPages: null, // Not stored in user requests
      processedSlug: data.processedSlug,
    });
  }

  // Sort by request count (most requested first), then by last requested
  items.sort((a, b) => {
    if (b.requestCount !== a.requestCount) {
      return b.requestCount - a.requestCount;
    }
    return b.lastRequestedAt.getTime() - a.lastRequestedAt.getTime();
  });

  // Apply pagination
  return items.slice(offset, offset + limit);
}

/**
 * Delete a user request by its internal ID.
 * @param requestId - The internal request ID
 * @returns True if deleted, false if not found
 */
export async function deleteRequestById(requestId: number): Promise<boolean> {
  try {
    await prisma.userRequest.delete({
      where: { id: BigInt(requestId) },
    });
    return true;
  } catch {
    return false;
  }
}

/**
 * Delete all user requests for a specific arXiv ID.
 * @param arxivId - The arXiv ID to delete requests for
 * @returns Number of requests deleted
 */
export async function deleteAllRequestsForArxiv(arxivId: string): Promise<number> {
  const result = await prisma.userRequest.deleteMany({
    where: { arxivId },
  });
  return result.count;
}

/**
 * Start processing a paper from a user request.
 * Creates a paper record if one doesn't exist for the arXiv ID.
 * @param arxivId - The arXiv ID to process
 * @returns Paper UUID and status
 */
export async function startProcessingRequest(
  arxivId: string
): Promise<StartProcessingResponse> {
  // Check if paper already exists
  const existingPaper = await prisma.paper.findUnique({
    where: { arxivId },
    select: { paperUuid: true, status: true },
  });

  if (existingPaper) {
    return {
      paperUuid: existingPaper.paperUuid,
      status: existingPaper.status,
    };
  }

  // Create new paper record with status 'not_started'
  const { randomUUID } = await import('crypto');
  const paperUuid = randomUUID();
  const now = new Date();

  const paper = await prisma.paper.create({
    data: {
      paperUuid,
      arxivId,
      arxivUrl: `https://arxiv.org/abs/${arxivId}`,
      status: 'not_started',
      createdAt: now,
      updatedAt: now,
    },
  });

  return {
    paperUuid: paper.paperUuid,
    status: paper.status,
  };
}

// ============================================================================
// MAIN HANDLERS - Processing Metrics
// ============================================================================

/**
 * Get processing metrics for a paper initiated by the user.
 * @param authProviderId - The user's auth provider ID
 * @param paperUuid - The paper UUID
 * @returns Processing metrics or null if paper not found or not initiated by user
 */
export async function getProcessingMetrics(
  authProviderId: string,
  paperUuid: string
): Promise<ProcessingMetrics | null> {
  const paper = await prisma.paper.findUnique({
    where: { paperUuid },
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
      initiatedByUserId: true,
    },
  });

  if (!paper) {
    return null;
  }

  // Verify the user initiated this paper
  if (paper.initiatedByUserId !== authProviderId) {
    return null;
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
