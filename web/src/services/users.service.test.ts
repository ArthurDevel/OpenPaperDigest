/**
 * Unit tests for the User Service
 *
 * Tests the business logic for:
 * - User list management (add, remove, check papers)
 * - User request management (paper processing requests)
 * - Aggregated request retrieval for admin
 * - Processing metrics retrieval
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// ============================================================================
// MOCK SETUP
// ============================================================================

// Use vi.hoisted to ensure mock functions are available when vi.mock runs
const {
  mockMaybeSingle,
  mockSingle,
  mockSelect,
  mockInsert,
  mockUpdate,
  mockDelete,
  mockEq,
  mockOrder,
  mockLimit,
  mockFrom,
} = vi.hoisted(() => {
  const mockMaybeSingle = vi.fn();
  const mockSingle = vi.fn();
  const mockLimit = vi.fn();
  const mockOrder = vi.fn();
  const mockEq = vi.fn();
  const mockSelect = vi.fn();
  const mockInsert = vi.fn();
  const mockUpdate = vi.fn();
  const mockDelete = vi.fn();
  const mockFrom = vi.fn();

  // Set up the chainable returns
  mockLimit.mockImplementation(() => ({
    maybeSingle: mockMaybeSingle,
  }));

  mockOrder.mockImplementation(() => ({
    limit: mockLimit,
    maybeSingle: mockMaybeSingle,
  }));

  mockEq.mockImplementation(() => ({
    eq: mockEq,
    order: mockOrder,
    limit: mockLimit,
    maybeSingle: mockMaybeSingle,
    single: mockSingle,
    select: mockSelect,
    delete: mockDelete,
  }));

  mockSelect.mockImplementation(() => ({
    eq: mockEq,
    order: mockOrder,
    limit: mockLimit,
    maybeSingle: mockMaybeSingle,
    single: mockSingle,
  }));

  mockInsert.mockImplementation(() => ({
    select: mockSelect,
    single: mockSingle,
  }));

  mockUpdate.mockImplementation(() => ({
    eq: mockEq,
    select: mockSelect,
    single: mockSingle,
  }));

  mockDelete.mockImplementation(() => ({
    eq: mockEq,
  }));

  mockFrom.mockImplementation(() => ({
    select: mockSelect,
    insert: mockInsert,
    update: mockUpdate,
    delete: mockDelete,
    eq: mockEq,
  }));

  return {
    mockMaybeSingle,
    mockSingle,
    mockSelect,
    mockInsert,
    mockUpdate,
    mockDelete,
    mockEq,
    mockOrder,
    mockLimit,
    mockFrom,
  };
});

vi.mock('@/lib/supabase/server', () => ({
  createClient: vi.fn().mockResolvedValue({
    from: mockFrom,
  }),
}));

import {
  addToList,
  removeFromList,
  isInList,
  addRequest,
  getAggregatedRequests,
  getProcessingMetrics,
} from './users.service';

// ============================================================================
// TEST SETUP
// ============================================================================

beforeEach(() => {
  vi.clearAllMocks();
  // Reset mockOrder to allow async resolution
  mockOrder.mockResolvedValue({ data: [], error: null });
});

// ============================================================================
// addToList TESTS
// ============================================================================

describe('addToList', () => {
  it('throws "Paper not found: {uuid}" when paper does not exist', async () => {
    // Paper not found
    mockMaybeSingle.mockResolvedValueOnce({ data: null, error: null });

    await expect(addToList('user-123', 'paper-uuid')).rejects.toThrow(
      'Paper not found: paper-uuid'
    );
  });

  it('returns { created: false } when paper is already in list', async () => {
    mockMaybeSingle
      // First call: paper exists
      .mockResolvedValueOnce({
        data: { id: 1 },
        error: null,
      })
      // Second call: list entry exists
      .mockResolvedValueOnce({
        data: {
          id: 1,
          user_id: 'user-123',
          paper_id: 1,
          created_at: new Date().toISOString(),
        },
        error: null,
      });

    const result = await addToList('user-123', 'paper-uuid');

    expect(result).toEqual({ created: false });
    expect(mockInsert).not.toHaveBeenCalled();
  });

  it('creates entry and returns { created: true } when paper is not in list', async () => {
    mockMaybeSingle
      // First call: paper exists
      .mockResolvedValueOnce({
        data: { id: 1 },
        error: null,
      })
      // Second call: list entry does not exist
      .mockResolvedValueOnce({ data: null, error: null });

    const result = await addToList('user-123', 'paper-uuid');

    expect(result).toEqual({ created: true });
    expect(mockInsert).toHaveBeenCalledWith(
      expect.objectContaining({
        user_id: 'user-123',
        paper_id: 1,
      })
    );
  });
});

// ============================================================================
// removeFromList TESTS
// ============================================================================

describe('removeFromList', () => {
  it('returns { deleted: false } when paper is not found', async () => {
    mockMaybeSingle.mockResolvedValue({ data: null, error: null });

    const result = await removeFromList('user-123', 'paper-uuid');

    expect(result).toEqual({ deleted: false });
    expect(mockDelete).not.toHaveBeenCalled();
  });

  it('returns { deleted: true } when entry is deleted', async () => {
    mockMaybeSingle
      // First call: paper exists
      .mockResolvedValueOnce({
        data: { id: 1 },
        error: null,
      })
      // Second call: list entry exists
      .mockResolvedValueOnce({
        data: { id: 1 },
        error: null,
      });

    const result = await removeFromList('user-123', 'paper-uuid');

    expect(result).toEqual({ deleted: true });
    expect(mockDelete).toHaveBeenCalled();
  });

  it('returns { deleted: false } when no entry exists to delete', async () => {
    mockMaybeSingle
      // First call: paper exists
      .mockResolvedValueOnce({
        data: { id: 1 },
        error: null,
      })
      // Second call: list entry does not exist
      .mockResolvedValueOnce({ data: null, error: null });

    const result = await removeFromList('user-123', 'paper-uuid');

    expect(result).toEqual({ deleted: false });
  });
});

// ============================================================================
// isInList TESTS
// ============================================================================

describe('isInList', () => {
  it('returns { exists: false } when paper is not found', async () => {
    mockMaybeSingle.mockResolvedValue({ data: null, error: null });

    const result = await isInList('user-123', 'paper-uuid');

    expect(result).toEqual({ exists: false });
  });

  it('returns { exists: true } when entry exists', async () => {
    mockMaybeSingle
      // First call: paper exists
      .mockResolvedValueOnce({
        data: { id: 1 },
        error: null,
      })
      // Second call: list entry exists
      .mockResolvedValueOnce({
        data: {
          id: 1,
          user_id: 'user-123',
          paper_id: 1,
          created_at: new Date().toISOString(),
        },
        error: null,
      });

    const result = await isInList('user-123', 'paper-uuid');

    expect(result).toEqual({ exists: true });
  });

  it('returns { exists: false } when entry does not exist', async () => {
    mockMaybeSingle
      // First call: paper exists
      .mockResolvedValueOnce({
        data: { id: 1 },
        error: null,
      })
      // Second call: list entry does not exist
      .mockResolvedValueOnce({ data: null, error: null });

    const result = await isInList('user-123', 'paper-uuid');

    expect(result).toEqual({ exists: false });
  });
});

// ============================================================================
// addRequest TESTS
// ============================================================================

describe('addRequest', () => {
  it('returns { created: false } when request already exists', async () => {
    // Request already exists
    mockMaybeSingle.mockResolvedValueOnce({
      data: {
        id: 1,
        user_id: 'user-123',
        arxiv_id: 'arxiv-123',
        title: 'Title',
        authors: 'Authors',
        created_at: new Date().toISOString(),
        is_processed: false,
        processed_slug: null,
      },
      error: null,
    });

    const result = await addRequest('user-123', 'arxiv-123', 'Title', 'Authors');

    expect(result).toEqual({ created: false });
    expect(mockInsert).not.toHaveBeenCalled();
  });

  it('creates request and returns { created: true } when request does not exist', async () => {
    // Request does not exist
    mockMaybeSingle.mockResolvedValueOnce({ data: null, error: null });

    const result = await addRequest('user-123', 'arxiv-123', 'Title', 'Authors');

    expect(result).toEqual({ created: true });
    expect(mockInsert).toHaveBeenCalledWith(
      expect.objectContaining({
        user_id: 'user-123',
        arxiv_id: 'arxiv-123',
        title: 'Title',
        authors: 'Authors',
        is_processed: false,
      })
    );
  });

  it('handles null title and authors', async () => {
    // Request does not exist
    mockMaybeSingle.mockResolvedValueOnce({ data: null, error: null });

    const result = await addRequest('user-123', 'arxiv-123', null, null);

    expect(result).toEqual({ created: true });
    expect(mockInsert).toHaveBeenCalledWith(
      expect.objectContaining({
        user_id: 'user-123',
        arxiv_id: 'arxiv-123',
        title: null,
        authors: null,
      })
    );
  });
});

// ============================================================================
// getAggregatedRequests TESTS
// ============================================================================

describe('getAggregatedRequests', () => {
  it('returns empty array when there are no requests', async () => {
    mockOrder.mockResolvedValue({ data: [], error: null });

    const result = await getAggregatedRequests();

    expect(result).toEqual([]);
  });

  it('returns single aggregated item with requestCount: 1 for single request', async () => {
    const createdAt = new Date('2024-01-15T10:00:00Z');

    mockOrder.mockResolvedValue({
      data: [
        {
          id: 1,
          user_id: 'user-123',
          arxiv_id: '2401.00001',
          title: 'Test Paper',
          authors: 'Test Author',
          created_at: createdAt.toISOString(),
          is_processed: false,
          processed_slug: null,
        },
      ],
      error: null,
    });

    const result = await getAggregatedRequests();

    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({
      arxivId: '2401.00001',
      arxivAbsUrl: 'https://arxiv.org/abs/2401.00001',
      arxivPdfUrl: 'https://arxiv.org/pdf/2401.00001.pdf',
      requestCount: 1,
      firstRequestedAt: createdAt,
      lastRequestedAt: createdAt,
      title: 'Test Paper',
      authors: 'Test Author',
      numPages: null,
      processedSlug: null,
    });
  });

  it('aggregates multiple requests for the same arxivId with correct requestCount', async () => {
    const firstDate = new Date('2024-01-10T10:00:00Z');
    const secondDate = new Date('2024-01-15T10:00:00Z');
    const thirdDate = new Date('2024-01-20T10:00:00Z');

    mockOrder.mockResolvedValue({
      data: [
        {
          id: 3,
          user_id: 'user-789',
          arxiv_id: '2401.00001',
          title: 'Test Paper',
          authors: 'Test Author',
          created_at: thirdDate.toISOString(),
          is_processed: false,
          processed_slug: null,
        },
        {
          id: 2,
          user_id: 'user-456',
          arxiv_id: '2401.00001',
          title: null,
          authors: null,
          created_at: secondDate.toISOString(),
          is_processed: false,
          processed_slug: null,
        },
        {
          id: 1,
          user_id: 'user-123',
          arxiv_id: '2401.00001',
          title: null,
          authors: null,
          created_at: firstDate.toISOString(),
          is_processed: false,
          processed_slug: null,
        },
      ],
      error: null,
    });

    const result = await getAggregatedRequests();

    expect(result).toHaveLength(1);
    expect(result[0].requestCount).toBe(3);
    expect(result[0].firstRequestedAt).toEqual(firstDate);
    expect(result[0].lastRequestedAt).toEqual(thirdDate);
    expect(result[0].title).toBe('Test Paper');
    expect(result[0].authors).toBe('Test Author');
  });

  it('sorts by requestCount (most requested first), then by lastRequestedAt', async () => {
    const now = new Date();
    const earlier = new Date(now.getTime() - 1000 * 60 * 60); // 1 hour earlier

    mockOrder.mockResolvedValue({
      data: [
        // Paper A: 1 request
        {
          id: 1,
          user_id: 'user-1',
          arxiv_id: 'paper-A',
          title: 'Paper A',
          authors: null,
          created_at: now.toISOString(),
          is_processed: false,
          processed_slug: null,
        },
        // Paper B: 2 requests
        {
          id: 2,
          user_id: 'user-1',
          arxiv_id: 'paper-B',
          title: 'Paper B',
          authors: null,
          created_at: earlier.toISOString(),
          is_processed: false,
          processed_slug: null,
        },
        {
          id: 3,
          user_id: 'user-2',
          arxiv_id: 'paper-B',
          title: null,
          authors: null,
          created_at: now.toISOString(),
          is_processed: false,
          processed_slug: null,
        },
        // Paper C: 2 requests but earlier lastRequestedAt
        {
          id: 4,
          user_id: 'user-1',
          arxiv_id: 'paper-C',
          title: 'Paper C',
          authors: null,
          created_at: earlier.toISOString(),
          is_processed: false,
          processed_slug: null,
        },
        {
          id: 5,
          user_id: 'user-2',
          arxiv_id: 'paper-C',
          title: null,
          authors: null,
          created_at: earlier.toISOString(),
          is_processed: false,
          processed_slug: null,
        },
      ],
      error: null,
    });

    const result = await getAggregatedRequests();

    expect(result).toHaveLength(3);
    // Paper B should be first (2 requests, later lastRequestedAt)
    expect(result[0].arxivId).toBe('paper-B');
    expect(result[0].requestCount).toBe(2);
    // Paper C should be second (2 requests, earlier lastRequestedAt)
    expect(result[1].arxivId).toBe('paper-C');
    expect(result[1].requestCount).toBe(2);
    // Paper A should be last (1 request)
    expect(result[2].arxivId).toBe('paper-A');
    expect(result[2].requestCount).toBe(1);
  });

  it('respects limit parameter', async () => {
    const now = new Date();

    mockOrder.mockResolvedValue({
      data: [
        {
          id: 1,
          user_id: 'user-1',
          arxiv_id: 'paper-A',
          title: 'Paper A',
          authors: null,
          created_at: now.toISOString(),
          is_processed: false,
          processed_slug: null,
        },
        {
          id: 2,
          user_id: 'user-1',
          arxiv_id: 'paper-B',
          title: 'Paper B',
          authors: null,
          created_at: now.toISOString(),
          is_processed: false,
          processed_slug: null,
        },
        {
          id: 3,
          user_id: 'user-1',
          arxiv_id: 'paper-C',
          title: 'Paper C',
          authors: null,
          created_at: now.toISOString(),
          is_processed: false,
          processed_slug: null,
        },
      ],
      error: null,
    });

    const result = await getAggregatedRequests(2);

    expect(result).toHaveLength(2);
  });

  it('respects offset parameter', async () => {
    const now = new Date();

    mockOrder.mockResolvedValue({
      data: [
        {
          id: 1,
          user_id: 'user-1',
          arxiv_id: 'paper-A',
          title: 'Paper A',
          authors: null,
          created_at: now.toISOString(),
          is_processed: false,
          processed_slug: null,
        },
        {
          id: 2,
          user_id: 'user-1',
          arxiv_id: 'paper-B',
          title: 'Paper B',
          authors: null,
          created_at: now.toISOString(),
          is_processed: false,
          processed_slug: null,
        },
        {
          id: 3,
          user_id: 'user-1',
          arxiv_id: 'paper-C',
          title: 'Paper C',
          authors: null,
          created_at: now.toISOString(),
          is_processed: false,
          processed_slug: null,
        },
      ],
      error: null,
    });

    const result = await getAggregatedRequests(10, 1);

    expect(result).toHaveLength(2);
  });

  it('handles processed requests correctly', async () => {
    const now = new Date();

    mockOrder.mockResolvedValue({
      data: [
        {
          id: 1,
          user_id: 'user-1',
          arxiv_id: 'paper-A',
          title: 'Paper A',
          authors: 'Author A',
          created_at: now.toISOString(),
          is_processed: false,
          processed_slug: null,
        },
        {
          id: 2,
          user_id: 'user-2',
          arxiv_id: 'paper-A',
          title: null,
          authors: null,
          created_at: now.toISOString(),
          is_processed: true,
          processed_slug: 'paper-a-slug',
        },
      ],
      error: null,
    });

    const result = await getAggregatedRequests();

    expect(result).toHaveLength(1);
    expect(result[0].processedSlug).toBe('paper-a-slug');
  });
});

// ============================================================================
// getProcessingMetrics TESTS
// ============================================================================

describe('getProcessingMetrics', () => {
  it('returns null when paper is not found', async () => {
    mockMaybeSingle.mockResolvedValue({ data: null, error: null });

    const result = await getProcessingMetrics('user-123', 'paper-uuid');

    expect(result).toBeNull();
  });

  it('returns null when paper was not initiated by user', async () => {
    mockMaybeSingle.mockResolvedValue({
      data: {
        paper_uuid: 'paper-uuid',
        status: 'completed',
        num_pages: 10,
        processing_time_seconds: 120,
        total_cost: 0.5,
        avg_cost_per_page: 0.05,
        started_at: new Date().toISOString(),
        finished_at: new Date().toISOString(),
        error_message: null,
        initiated_by_user_id: 'different-user',
      },
      error: null,
    });

    const result = await getProcessingMetrics('user-123', 'paper-uuid');

    expect(result).toBeNull();
  });

  it('returns metrics when paper was initiated by user', async () => {
    const startedAt = new Date('2024-01-15T10:00:00Z');
    const finishedAt = new Date('2024-01-15T10:02:00Z');

    mockMaybeSingle.mockResolvedValue({
      data: {
        paper_uuid: 'paper-uuid',
        status: 'completed',
        num_pages: 10,
        processing_time_seconds: 120,
        total_cost: 0.5,
        avg_cost_per_page: 0.05,
        started_at: startedAt.toISOString(),
        finished_at: finishedAt.toISOString(),
        error_message: null,
        initiated_by_user_id: 'user-123',
      },
      error: null,
    });

    const result = await getProcessingMetrics('user-123', 'paper-uuid');

    expect(result).toEqual({
      paperUuid: 'paper-uuid',
      status: 'completed',
      numPages: 10,
      processingTimeSeconds: 120,
      totalCost: 0.5,
      avgCostPerPage: 0.05,
      startedAt,
      finishedAt,
      errorMessage: null,
    });
  });

  it('returns metrics with error message for failed paper', async () => {
    const startedAt = new Date('2024-01-15T10:00:00Z');

    mockMaybeSingle.mockResolvedValue({
      data: {
        paper_uuid: 'paper-uuid',
        status: 'failed',
        num_pages: null,
        processing_time_seconds: null,
        total_cost: null,
        avg_cost_per_page: null,
        started_at: startedAt.toISOString(),
        finished_at: null,
        error_message: 'Processing failed due to timeout',
        initiated_by_user_id: 'user-123',
      },
      error: null,
    });

    const result = await getProcessingMetrics('user-123', 'paper-uuid');

    expect(result).toEqual({
      paperUuid: 'paper-uuid',
      status: 'failed',
      numPages: null,
      processingTimeSeconds: null,
      totalCost: null,
      avgCostPerPage: null,
      startedAt,
      finishedAt: null,
      errorMessage: 'Processing failed due to timeout',
    });
  });
});
