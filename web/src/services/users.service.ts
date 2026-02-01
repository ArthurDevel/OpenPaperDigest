/**
 * User Service
 *
 * Provides business logic for user-related operations.
 * - User sync from BetterAuth authentication hooks
 * - User list management (add, remove, check papers)
 * - User request management (paper processing requests)
 */

import { createClient } from '@/lib/supabase/server';
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
import type { Tables, TablesInsert } from '@/lib/types/database.types';

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
  const supabase = await createClient();

  const { data: existingData, error: findError } = await supabase
    .from('users')
    .select()
    .eq('id', payload.id)
    .maybeSingle();

  if (findError) throw new Error(findError.message);

  const existing = existingData as Tables<'users'> | null;

  if (existing) {
    return { created: false };
  }

  const insertData: TablesInsert<'users'> = {
    id: payload.id,
    email: payload.email,
    created_at: new Date().toISOString(),
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { error: createError } = await (supabase
    .from('users') as any)
    .insert(insertData);

  if (createError) throw new Error(createError.message);

  return { created: true };
}

/**
 * Get a user record by their auth provider ID.
 * @param authProviderId - The user's ID from BetterAuth
 * @returns User record or null if not found
 */
export async function getUserByAuthProviderId(authProviderId: string): Promise<User | null> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from('users')
    .select()
    .eq('id', authProviderId)
    .maybeSingle();

  if (error) throw new Error(error.message);

  const user = data as Tables<'users'> | null;

  if (!user) {
    return null;
  }

  return {
    id: user.id,
    email: user.email,
    createdAt: new Date(user.created_at),
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
  const supabase = await createClient();

  // Verify user exists
  const { data: userData, error: userError } = await supabase
    .from('users')
    .select()
    .eq('id', authProviderId)
    .maybeSingle();

  if (userError) throw new Error(userError.message);

  const user = userData as Tables<'users'> | null;

  if (!user) {
    throw new Error(`User not found: ${authProviderId}`);
  }

  // Verify paper exists and get its internal ID
  const { data: paperData, error: paperError } = await supabase
    .from('papers')
    .select('id')
    .eq('paper_uuid', paperUuid)
    .maybeSingle();

  if (paperError) throw new Error(paperError.message);

  const paper = paperData as Tables<'papers'> | null;

  if (!paper) {
    throw new Error(`Paper not found: ${paperUuid}`);
  }

  // Check if already in list (compound unique lookup)
  const { data: existingData, error: existingError } = await supabase
    .from('user_lists')
    .select()
    .eq('user_id', authProviderId)
    .eq('paper_id', paper.id)
    .maybeSingle();

  if (existingError) throw new Error(existingError.message);

  const existing = existingData as Tables<'user_lists'> | null;

  if (existing) {
    return { created: false };
  }

  const insertData: TablesInsert<'user_lists'> = {
    user_id: authProviderId,
    paper_id: paper.id,
    created_at: new Date().toISOString(),
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { error: createError } = await (supabase
    .from('user_lists') as any)
    .insert(insertData);

  if (createError) throw new Error(createError.message);

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
  const supabase = await createClient();

  // Get paper internal ID
  const { data: paperData, error: paperError } = await supabase
    .from('papers')
    .select('id')
    .eq('paper_uuid', paperUuid)
    .maybeSingle();

  if (paperError) throw new Error(paperError.message);

  const paper = paperData as Tables<'papers'> | null;

  if (!paper) {
    return { deleted: false };
  }

  // Check if entry exists before deleting
  const { data: existingData, error: existingError } = await supabase
    .from('user_lists')
    .select('id')
    .eq('user_id', authProviderId)
    .eq('paper_id', paper.id)
    .maybeSingle();

  if (existingError) throw new Error(existingError.message);

  const existing = existingData as Tables<'user_lists'> | null;

  if (!existing) {
    return { deleted: false };
  }

  // Delete the list entry
  const { error: deleteError } = await supabase
    .from('user_lists')
    .delete()
    .eq('user_id', authProviderId)
    .eq('paper_id', paper.id);

  if (deleteError) throw new Error(deleteError.message);

  return { deleted: true };
}

/**
 * Get all papers in a user's saved list.
 * @param authProviderId - The user's auth provider ID
 * @returns Array of papers in the user's list with metadata
 */
export async function getList(authProviderId: string): Promise<UserListItem[]> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from('user_lists')
    .select(`
      created_at,
      papers (
        paper_uuid,
        title,
        authors,
        thumbnail_data_url
      )
    `)
    .eq('user_id', authProviderId)
    .order('created_at', { ascending: false });

  if (error) throw new Error(error.message);

  // Type the join result explicitly (Supabase doesn't infer nested selects well)
  const listItems = (data ?? []) as Array<{
    created_at: string;
    papers: { paper_uuid: string; title: string | null; authors: string | null; thumbnail_data_url: string | null } | null;
  }>;

  // Get paper_uuids to fetch slugs separately
  const paperUuids = listItems
    .map((item) => item.papers?.paper_uuid)
    .filter((uuid): uuid is string => uuid != null);

  // Fetch active slugs for all papers
  const { data: slugsData, error: slugsError } = await supabase
    .from('paper_slugs')
    .select('paper_uuid, slug, created_at')
    .in('paper_uuid', paperUuids)
    .eq('tombstone', false)
    .order('created_at', { ascending: false });

  if (slugsError) throw new Error(slugsError.message);

  const slugs = (slugsData ?? []) as Tables<'paper_slugs'>[];

  // Build a map of paper_uuid -> most recent slug
  const slugMap = new Map<string, string>();
  for (const slug of slugs) {
    if (slug.paper_uuid && !slugMap.has(slug.paper_uuid)) {
      slugMap.set(slug.paper_uuid, slug.slug);
    }
  }

  return listItems.map((item) => ({
    paperUuid: item.papers?.paper_uuid ?? '',
    title: item.papers?.title ?? null,
    authors: item.papers?.authors ?? null,
    thumbnailDataUrl: item.papers?.thumbnail_data_url ?? null,
    slug: item.papers?.paper_uuid ? slugMap.get(item.papers.paper_uuid) ?? null : null,
    createdAt: new Date(item.created_at),
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
  const supabase = await createClient();

  // Get paper internal ID
  const { data: paperData, error: paperError } = await supabase
    .from('papers')
    .select('id')
    .eq('paper_uuid', paperUuid)
    .maybeSingle();

  if (paperError) throw new Error(paperError.message);

  const paper = paperData as Tables<'papers'> | null;

  if (!paper) {
    return { exists: false };
  }

  const { data: existingData, error: existingError } = await supabase
    .from('user_lists')
    .select('id')
    .eq('user_id', authProviderId)
    .eq('paper_id', paper.id)
    .maybeSingle();

  if (existingError) throw new Error(existingError.message);

  const existing = existingData as Tables<'user_lists'> | null;

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
  const supabase = await createClient();

  // Verify user exists
  const { data: userData, error: userError } = await supabase
    .from('users')
    .select()
    .eq('id', authProviderId)
    .maybeSingle();

  if (userError) throw new Error(userError.message);

  const user = userData as Tables<'users'> | null;

  if (!user) {
    throw new Error(`User not found: ${authProviderId}`);
  }

  // Check if request already exists (compound unique lookup)
  const { data: existingData, error: existingError } = await supabase
    .from('user_requests')
    .select()
    .eq('user_id', authProviderId)
    .eq('arxiv_id', arxivId)
    .maybeSingle();

  if (existingError) throw new Error(existingError.message);

  const existing = existingData as Tables<'user_requests'> | null;

  if (existing) {
    return { created: false };
  }

  const insertData: TablesInsert<'user_requests'> = {
    user_id: authProviderId,
    arxiv_id: arxivId,
    title,
    authors,
    created_at: new Date().toISOString(),
    is_processed: false,
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { error: createError } = await (supabase
    .from('user_requests') as any)
    .insert(insertData);

  if (createError) throw new Error(createError.message);

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
  const supabase = await createClient();

  // Check if request exists before deleting
  const { data: existingData, error: existingError } = await supabase
    .from('user_requests')
    .select('id')
    .eq('user_id', authProviderId)
    .eq('arxiv_id', arxivId)
    .maybeSingle();

  if (existingError) throw new Error(existingError.message);

  const existing = existingData as Tables<'user_requests'> | null;

  if (!existing) {
    return { deleted: false };
  }

  const { error: deleteError } = await supabase
    .from('user_requests')
    .delete()
    .eq('user_id', authProviderId)
    .eq('arxiv_id', arxivId);

  if (deleteError) throw new Error(deleteError.message);

  return { deleted: true };
}

/**
 * Get all paper requests for a user.
 * @param authProviderId - The user's auth provider ID
 * @returns Array of user's paper requests with metadata
 */
export async function listRequests(authProviderId: string): Promise<UserRequestItem[]> {
  const supabase = await createClient();

  const { data: requestsData, error } = await supabase
    .from('user_requests')
    .select()
    .eq('user_id', authProviderId)
    .order('created_at', { ascending: false });

  if (error) throw new Error(error.message);

  const requests = (requestsData ?? []) as Tables<'user_requests'>[];

  return requests.map((request) => ({
    arxivId: request.arxiv_id,
    title: request.title,
    authors: request.authors,
    createdAt: new Date(request.created_at),
    isProcessed: request.is_processed,
    processedSlug: request.processed_slug,
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
  const supabase = await createClient();

  const { data: existingData, error } = await supabase
    .from('user_requests')
    .select('id')
    .eq('user_id', authProviderId)
    .eq('arxiv_id', arxivId)
    .maybeSingle();

  if (error) throw new Error(error.message);

  const existing = existingData as Tables<'user_requests'> | null;

  return { exists: !!existing };
}

/**
 * Get all paper requests from all users (admin only).
 * Returns requests with user email for admin display.
 * @returns Array of all paper requests with user email
 */
export async function getAllRequests(): Promise<AdminRequestItem[]> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from('user_requests')
    .select(`
      id,
      user_id,
      arxiv_id,
      title,
      authors,
      created_at,
      is_processed,
      processed_slug,
      users (
        email
      )
    `)
    .order('created_at', { ascending: false });

  if (error) throw new Error(error.message);

  // Type the join result explicitly (Supabase doesn't infer nested selects well)
  const requests = (data ?? []) as Array<{
    id: number;
    user_id: string;
    arxiv_id: string;
    title: string | null;
    authors: string | null;
    created_at: string;
    is_processed: boolean;
    processed_slug: string | null;
    users: { email: string } | null;
  }>;

  return requests.map((request) => ({
    id: request.id,
    userId: request.user_id,
    userEmail: request.users?.email ?? '',
    arxivId: request.arxiv_id,
    title: request.title,
    authors: request.authors,
    createdAt: new Date(request.created_at),
    isProcessed: request.is_processed,
    processedSlug: request.processed_slug,
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
  const supabase = await createClient();

  // Get all requests grouped by arxivId
  const { data, error } = await supabase
    .from('user_requests')
    .select('*')
    .order('created_at', { ascending: false });

  if (error) throw new Error(error.message);

  const requests = (data ?? []) as Tables<'user_requests'>[];

  // Group by arxivId
  const grouped = new Map<string, {
    arxivId: string;
    requests: Tables<'user_requests'>[];
    title: string | null;
    authors: string | null;
    isProcessed: boolean;
    processedSlug: string | null;
  }>();

  for (const req of requests) {
    const existing = grouped.get(req.arxiv_id);
    if (existing) {
      existing.requests.push(req);
      // Update title/authors if not set
      if (!existing.title && req.title) existing.title = req.title;
      if (!existing.authors && req.authors) existing.authors = req.authors;
      // Mark as processed if any request is processed
      if (req.is_processed) {
        existing.isProcessed = true;
        existing.processedSlug = req.processed_slug;
      }
    } else {
      grouped.set(req.arxiv_id, {
        arxivId: req.arxiv_id,
        requests: [req],
        title: req.title,
        authors: req.authors,
        isProcessed: req.is_processed,
        processedSlug: req.processed_slug,
      });
    }
  }

  // Convert to array and calculate aggregates
  const items: AggregatedRequestItem[] = [];
  for (const [arxivId, data] of grouped) {
    const sortedRequests = data.requests.sort(
      (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    );
    items.push({
      arxivId,
      arxivAbsUrl: `https://arxiv.org/abs/${arxivId}`,
      arxivPdfUrl: `https://arxiv.org/pdf/${arxivId}.pdf`,
      requestCount: data.requests.length,
      firstRequestedAt: new Date(sortedRequests[0].created_at),
      lastRequestedAt: new Date(sortedRequests[sortedRequests.length - 1].created_at),
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
  const supabase = await createClient();

  // Check if request exists before deleting
  const { data: existingData, error: existingError } = await supabase
    .from('user_requests')
    .select('id')
    .eq('id', requestId)
    .maybeSingle();

  if (existingError) throw new Error(existingError.message);

  const existing = existingData as Tables<'user_requests'> | null;

  if (!existing) {
    return false;
  }

  const { error: deleteError } = await supabase
    .from('user_requests')
    .delete()
    .eq('id', requestId);

  if (deleteError) throw new Error(deleteError.message);

  return true;
}

/**
 * Delete all user requests for a specific arXiv ID.
 * @param arxivId - The arXiv ID to delete requests for
 * @returns Number of requests deleted
 */
export async function deleteAllRequestsForArxiv(arxivId: string): Promise<number> {
  const supabase = await createClient();

  // Count existing requests before deleting (Supabase doesn't return count directly)
  const { data: existingData, error: countError } = await supabase
    .from('user_requests')
    .select('id')
    .eq('arxiv_id', arxivId);

  if (countError) throw new Error(countError.message);

  const existing = (existingData ?? []) as Tables<'user_requests'>[];
  const count = existing.length;

  if (count === 0) {
    return 0;
  }

  const { error: deleteError } = await supabase
    .from('user_requests')
    .delete()
    .eq('arxiv_id', arxivId);

  if (deleteError) throw new Error(deleteError.message);

  return count;
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
  const supabase = await createClient();

  // Check if paper already exists
  const { data: existingPaperData, error: findError } = await supabase
    .from('papers')
    .select('paper_uuid, status')
    .eq('arxiv_id', arxivId)
    .maybeSingle();

  if (findError) throw new Error(findError.message);

  const existingPaper = existingPaperData as Tables<'papers'> | null;

  if (existingPaper) {
    return {
      paperUuid: existingPaper.paper_uuid,
      status: existingPaper.status,
    };
  }

  // Create new paper record with status 'not_started'
  const { randomUUID } = await import('crypto');
  const paperUuid = randomUUID();
  const now = new Date().toISOString();

  const insertData: TablesInsert<'papers'> = {
    paper_uuid: paperUuid,
    arxiv_id: arxivId,
    arxiv_url: `https://arxiv.org/abs/${arxivId}`,
    status: 'not_started',
    created_at: now,
    updated_at: now,
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: paperData, error: createError } = await (supabase
    .from('papers') as any)
    .insert(insertData)
    .select('paper_uuid, status')
    .single();

  if (createError) throw new Error(createError.message);

  const paper = paperData as Tables<'papers'>;

  return {
    paperUuid: paper.paper_uuid,
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
      error_message,
      initiated_by_user_id
    `)
    .eq('paper_uuid', paperUuid)
    .maybeSingle();

  if (error) throw new Error(error.message);

  const paper = data as Tables<'papers'> | null;

  if (!paper) {
    return null;
  }

  // Verify the user initiated this paper
  if (paper.initiated_by_user_id !== authProviderId) {
    return null;
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
