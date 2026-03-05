/**
 * Unit tests for papers.service.ts
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
  mockIn,
  mockOrder,
  mockLimit,
  mockRange,
  mockFrom,
} = vi.hoisted(() => {
  const mockMaybeSingle = vi.fn();
  const mockSingle = vi.fn();
  const mockLimit = vi.fn();
  const mockRange = vi.fn();
  const mockOrder = vi.fn();
  const mockIn = vi.fn();
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

  mockRange.mockImplementation(() => ({
    maybeSingle: mockMaybeSingle,
  }));

  mockOrder.mockImplementation(() => ({
    limit: mockLimit,
    range: mockRange,
    maybeSingle: mockMaybeSingle,
  }));

  mockIn.mockImplementation(() => ({
    eq: mockEq,
    order: mockOrder,
    limit: mockLimit,
    range: mockRange,
    maybeSingle: mockMaybeSingle,
    single: mockSingle,
  }));

  mockEq.mockImplementation(() => ({
    eq: mockEq,
    order: mockOrder,
    limit: mockLimit,
    range: mockRange,
    maybeSingle: mockMaybeSingle,
    single: mockSingle,
    select: mockSelect,
    in: mockIn,
  }));

  mockSelect.mockImplementation(() => ({
    eq: mockEq,
    order: mockOrder,
    limit: mockLimit,
    range: mockRange,
    maybeSingle: mockMaybeSingle,
    single: mockSingle,
    in: mockIn,
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
    mockIn,
    mockOrder,
    mockLimit,
    mockRange,
    mockFrom,
  };
});

vi.mock('@/lib/supabase/server', () => ({
  createClient: vi.fn().mockResolvedValue({
    from: mockFrom,
  }),
}));

// Mock the arxiv module
vi.mock('@/lib/arxiv', () => ({
  normalizeId: vi.fn((url: string) => {
    if (url.includes('2301.12345')) {
      return { arxivId: '2301.12345', version: null };
    }
    if (url.includes('2302.99999v2')) {
      return { arxivId: '2302.99999', version: 'v2' };
    }
    throw new Error('Invalid arXiv ID');
  }),
}));

// Mock the slugs service
vi.mock('@/services/slugs.service', () => ({
  resolveSlug: vi.fn(),
  buildPaperSlug: vi.fn(() => 'test-slug'),
}));

// Mock crypto
vi.mock('crypto', () => ({
  randomUUID: vi.fn(() => 'mock-uuid-1234'),
}));

// Mock storage helpers (async signed URL functions)
vi.mock('@/lib/supabase/storage', () => ({
  getPaperThumbnailUrl: vi.fn(async (uuid: string) => `https://storage.test/papers/${uuid}/thumbnail.png`),
  getPaperFigureUrl: vi.fn(async (_uuid: string, figureId: string) => `https://storage.test/papers/${_uuid}/figures/${figureId}.png`),
  downloadPaperContent: vi.fn(),
  downloadPaperMarkdown: vi.fn(),
  deletePaperAssets: vi.fn(),
}));

import {
  getPaperSummary,
  getPaperMarkdown,
  checkArxivExists,
  enqueueArxiv,
  listMinimalPapers,
  restartPaper,
} from './papers.service';
import { downloadPaperMarkdown } from '@/lib/supabase/storage';

// ============================================================================
// TESTS
// ============================================================================

describe('papers.service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset mockRange and mockOrder to handle chaining
    mockRange.mockResolvedValue({ data: [], error: null });
    mockOrder.mockReturnValue({
      limit: mockLimit,
      range: mockRange,
      maybeSingle: mockMaybeSingle,
    });
  });

  // --------------------------------------------------------------------------
  // getPaperSummary - Summary extraction from summaries column
  // --------------------------------------------------------------------------
  describe('getPaperSummary', () => {
    it('extracts five_minute_summary from summaries column', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: {
          paper_uuid: 'test-uuid',
          title: 'Test Paper',
          authors: 'John Doe',
          arxiv_url: 'https://arxiv.org/abs/2301.12345',
          summaries: { five_minute_summary: 'This is a summary.' },
          num_pages: 10,
        },
        error: null,
      });

      const result = await getPaperSummary('test-uuid');

      expect(result.fiveMinuteSummary).toBe('This is a summary.');
      expect(result.paperId).toBe('test-uuid');
      expect(result.title).toBe('Test Paper');
      expect(result.pageCount).toBe(10);
      expect(result.thumbnailUrl).toBe('https://storage.test/papers/test-uuid/thumbnail.png');
    });

    it('returns null fiveMinuteSummary when summaries is null', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: {
          paper_uuid: 'test-uuid',
          title: 'Test Paper',
          authors: null,
          arxiv_url: null,
          summaries: null,
          num_pages: null,
        },
        error: null,
      });

      const result = await getPaperSummary('test-uuid');

      expect(result.fiveMinuteSummary).toBeNull();
      expect(result.pageCount).toBe(0);
    });

    it('returns null fiveMinuteSummary when five_minute_summary key is missing', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: {
          paper_uuid: 'test-uuid',
          title: 'Test Paper',
          authors: null,
          arxiv_url: null,
          summaries: { other_field: 'value' },
          num_pages: 5,
        },
        error: null,
      });

      const result = await getPaperSummary('test-uuid');

      expect(result.fiveMinuteSummary).toBeNull();
    });

    it('throws when paper not found', async () => {
      mockMaybeSingle.mockResolvedValue({ data: null, error: null });

      await expect(getPaperSummary('nonexistent')).rejects.toThrow(
        'Paper not found: nonexistent'
      );
    });
  });

  // --------------------------------------------------------------------------
  // getPaperMarkdown - Markdown from Supabase Storage
  // --------------------------------------------------------------------------
  describe('getPaperMarkdown', () => {
    it('returns markdown from storage when paper exists', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: { paper_uuid: 'test-uuid' },
        error: null,
      });
      vi.mocked(downloadPaperMarkdown).mockResolvedValue('# Paper Title\n\nContent here.');

      const result = await getPaperMarkdown('test-uuid');

      expect(result).toBe('# Paper Title\n\nContent here.');
      expect(downloadPaperMarkdown).toHaveBeenCalledWith('test-uuid');
    });

    it('throws when paper not found in DB', async () => {
      mockMaybeSingle.mockResolvedValue({ data: null, error: null });

      await expect(getPaperMarkdown('nonexistent')).rejects.toThrow(
        'Paper not found: nonexistent'
      );
    });
  });

  // --------------------------------------------------------------------------
  // checkArxivExists - Check if arXiv paper exists and is completed
  // --------------------------------------------------------------------------
  describe('checkArxivExists', () => {
    it('returns exists: true with slug-based viewerUrl when paper completed with slug', async () => {
      // First call: papers query
      mockMaybeSingle.mockResolvedValueOnce({
        data: { paper_uuid: 'test-uuid', status: 'completed' },
        error: null,
      });
      // Second call: paper_slugs query
      mockMaybeSingle.mockResolvedValueOnce({
        data: { slug: 'test-paper-slug' },
        error: null,
      });

      const result = await checkArxivExists('2301.12345');

      expect(result.exists).toBe(true);
      expect(result.viewerUrl).toBe('/paper/test-paper-slug');
    });

    it('returns exists: true with uuid-based viewerUrl when paper completed without slug', async () => {
      // First call: papers query
      mockMaybeSingle.mockResolvedValueOnce({
        data: { paper_uuid: 'test-uuid', status: 'completed' },
        error: null,
      });
      // Second call: paper_slugs query - no slug found
      mockMaybeSingle.mockResolvedValueOnce({
        data: null,
        error: null,
      });

      const result = await checkArxivExists('2301.12345');

      expect(result.exists).toBe(true);
      expect(result.viewerUrl).toBe('/paper/test-uuid');
    });

    it('returns exists: false when paper is not completed', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: {
          paper_uuid: 'test-uuid',
          status: 'processing',
          paper_slugs: [],
        },
        error: null,
      });

      const result = await checkArxivExists('2301.12345');

      expect(result.exists).toBe(false);
      expect(result.viewerUrl).toBeNull();
    });

    it('returns exists: false when paper not found', async () => {
      mockMaybeSingle.mockResolvedValue({ data: null, error: null });

      const result = await checkArxivExists('2301.12345');

      expect(result.exists).toBe(false);
      expect(result.viewerUrl).toBeNull();
    });
  });

  // --------------------------------------------------------------------------
  // enqueueArxiv - Create paper record for processing
  // --------------------------------------------------------------------------
  describe('enqueueArxiv', () => {
    it('returns existing paper info when paper already exists', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: {
          id: 42,
          paper_uuid: 'existing-uuid',
          status: 'completed',
        },
        error: null,
      });

      const result = await enqueueArxiv('https://arxiv.org/abs/2301.12345');

      expect(result).toEqual({
        jobDbId: 42,
        paperUuid: 'existing-uuid',
        status: 'completed',
      });
      expect(mockInsert).not.toHaveBeenCalled();
    });

    it('creates new paper record when paper does not exist', async () => {
      mockMaybeSingle.mockResolvedValue({ data: null, error: null });
      mockSingle.mockResolvedValue({
        data: {
          id: 99,
          paper_uuid: 'mock-uuid-1234',
          status: 'not_started',
        },
        error: null,
      });

      const result = await enqueueArxiv('https://arxiv.org/abs/2301.12345');

      expect(result).toEqual({
        jobDbId: 99,
        paperUuid: 'mock-uuid-1234',
        status: 'not_started',
      });
      expect(mockInsert).toHaveBeenCalledWith(
        expect.objectContaining({
          paper_uuid: 'mock-uuid-1234',
          arxiv_id: '2301.12345',
          arxiv_version: null,
          arxiv_url: 'https://arxiv.org/abs/2301.12345',
          status: 'not_started',
        })
      );
    });

    it('includes version in arxivUrl when version is present', async () => {
      mockMaybeSingle.mockResolvedValue({ data: null, error: null });
      mockSingle.mockResolvedValue({
        data: {
          id: 99,
          paper_uuid: 'mock-uuid-1234',
          status: 'not_started',
        },
        error: null,
      });

      await enqueueArxiv('https://arxiv.org/abs/2302.99999v2');

      expect(mockInsert).toHaveBeenCalledWith(
        expect.objectContaining({
          arxiv_id: '2302.99999',
          arxiv_version: 'v2',
          arxiv_url: 'https://arxiv.org/abs/2302.99999v2',
        })
      );
    });
  });

  // --------------------------------------------------------------------------
  // listMinimalPapers - Paginated paper list (no count query, uses hasMore detection)
  // --------------------------------------------------------------------------
  describe('listMinimalPapers', () => {
    it('returns paginated list with hasMore true when more items exist', async () => {
      // Mock for papers query - returns limit+1 items to indicate hasMore
      mockOrder.mockImplementationOnce(() => ({
        range: () => Promise.resolve({
          data: [
            { paper_uuid: 'uuid-1', title: 'Paper 1', authors: 'Author 1' },
            { paper_uuid: 'uuid-2', title: 'Paper 2', authors: 'Author 2' },
            { paper_uuid: 'uuid-3', title: 'Paper 3', authors: 'Author 3' }, // extra item
          ],
          error: null,
        }),
      }));

      // Mock for slugs query
      mockOrder.mockResolvedValueOnce({
        data: [{ paper_uuid: 'uuid-1', slug: 'paper-1-slug' }],
        error: null,
      });

      const result = await listMinimalPapers(1, 2);

      expect(result.items).toHaveLength(2); // Only returns limit items
      expect(result.page).toBe(1);
      expect(result.limit).toBe(2);
      expect(result.hasMore).toBe(true);
    });

    it('defaults to page 1 and limit 20', async () => {
      // Mock for papers query - empty result
      mockOrder.mockImplementationOnce(() => ({
        range: () => Promise.resolve({ data: [], error: null }),
      }));

      // Mock for slugs query
      mockOrder.mockResolvedValueOnce({ data: [], error: null });

      const result = await listMinimalPapers();

      expect(result.page).toBe(1);
      expect(result.limit).toBe(20);
    });

    it('maps slug correctly from separate slugs query', async () => {
      // Mock for papers query
      mockOrder.mockImplementationOnce(() => ({
        range: () => Promise.resolve({
          data: [{ paper_uuid: 'uuid-1', title: 'Paper 1', authors: null }],
          error: null,
        }),
      }));

      // Mock for slugs query
      mockOrder.mockResolvedValueOnce({
        data: [{ paper_uuid: 'uuid-1', slug: 'my-paper-slug' }],
        error: null,
      });

      const result = await listMinimalPapers(1, 10);

      expect(result.items[0].slug).toBe('my-paper-slug');
    });

    it('sets slug to null when no slugs exist', async () => {
      // Mock for papers query
      mockOrder.mockImplementationOnce(() => ({
        range: () => Promise.resolve({
          data: [{ paper_uuid: 'uuid-1', title: 'Paper 1', authors: null }],
          error: null,
        }),
      }));

      // Mock for slugs query - empty result
      mockOrder.mockResolvedValueOnce({ data: [], error: null });

      const result = await listMinimalPapers(1, 10);

      expect(result.items[0].slug).toBeNull();
    });

    it('calculates hasMore as false when fewer items than limit+1', async () => {
      // Mock for papers query - only 1 item returned (less than limit+1)
      mockOrder.mockImplementationOnce(() => ({
        range: () => Promise.resolve({
          data: [{ paper_uuid: 'uuid-1', title: 'Paper', authors: null }],
          error: null,
        }),
      }));

      // Mock for slugs query
      mockOrder.mockResolvedValueOnce({ data: [], error: null });

      const result = await listMinimalPapers(2, 2);

      expect(result.hasMore).toBe(false);
    });
  });

  // --------------------------------------------------------------------------
  // restartPaper - Reset paper status for reprocessing
  // --------------------------------------------------------------------------
  describe('restartPaper', () => {
    it('resets paper status to not_started when paper found and not processing', async () => {
      const now = new Date();
      mockMaybeSingle.mockResolvedValue({
        data: {
          id: 1,
          status: 'failed',
        },
        error: null,
      });
      mockSingle.mockResolvedValue({
        data: {
          paper_uuid: 'test-uuid',
          status: 'not_started',
          error_message: null,
          created_at: now.toISOString(),
          updated_at: now.toISOString(),
          started_at: null,
          finished_at: null,
          arxiv_id: '2301.12345',
          arxiv_version: null,
          arxiv_url: 'https://arxiv.org/abs/2301.12345',
          title: 'Test Paper',
          authors: 'Author',
          num_pages: 10,
          processing_time_seconds: null,
          total_cost: null,
          avg_cost_per_page: null,
        },
        error: null,
      });

      const result = await restartPaper('test-uuid');

      expect(result.status).toBe('not_started');
      expect(result.errorMessage).toBeNull();
      expect(mockUpdate).toHaveBeenCalledWith(
        expect.objectContaining({
          status: 'not_started',
          error_message: null,
          started_at: null,
          finished_at: null,
        })
      );
    });

    it('throws when paper not found', async () => {
      mockMaybeSingle.mockResolvedValue({ data: null, error: null });

      await expect(restartPaper('nonexistent')).rejects.toThrow(
        'Paper not found: nonexistent'
      );
    });

    it('throws when paper is already processing', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: {
          id: 1,
          status: 'processing',
        },
        error: null,
      });

      await expect(restartPaper('test-uuid')).rejects.toThrow(
        'Paper is already processing'
      );
    });

    it('allows restart when paper status is completed', async () => {
      const now = new Date();
      mockMaybeSingle.mockResolvedValue({
        data: {
          id: 1,
          status: 'completed',
        },
        error: null,
      });
      mockSingle.mockResolvedValue({
        data: {
          paper_uuid: 'test-uuid',
          status: 'not_started',
          error_message: null,
          created_at: now.toISOString(),
          updated_at: now.toISOString(),
          started_at: null,
          finished_at: null,
          arxiv_id: '2301.12345',
          arxiv_version: null,
          arxiv_url: 'https://arxiv.org/abs/2301.12345',
          title: 'Test Paper',
          authors: 'Author',
          num_pages: 10,
          processing_time_seconds: null,
          total_cost: null,
          avg_cost_per_page: null,
        },
        error: null,
      });

      const result = await restartPaper('test-uuid');

      expect(result.status).toBe('not_started');
    });

    it('allows restart when paper status is not_started', async () => {
      const now = new Date();
      mockMaybeSingle.mockResolvedValue({
        data: {
          id: 1,
          status: 'not_started',
        },
        error: null,
      });
      mockSingle.mockResolvedValue({
        data: {
          paper_uuid: 'test-uuid',
          status: 'not_started',
          error_message: null,
          created_at: now.toISOString(),
          updated_at: now.toISOString(),
          started_at: null,
          finished_at: null,
          arxiv_id: null,
          arxiv_version: null,
          arxiv_url: null,
          title: null,
          authors: null,
          num_pages: null,
          processing_time_seconds: null,
          total_cost: null,
          avg_cost_per_page: null,
        },
        error: null,
      });

      const result = await restartPaper('test-uuid');

      expect(result.status).toBe('not_started');
    });
  });
});
