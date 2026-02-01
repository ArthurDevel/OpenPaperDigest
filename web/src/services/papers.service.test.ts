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

import {
  getThumbnail,
  getPaperSummary,
  getPaperMarkdown,
  checkArxivExists,
  enqueueArxiv,
  listMinimalPapers,
  restartPaper,
} from './papers.service';

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
  // getThumbnail - Base64 data URL parsing
  // --------------------------------------------------------------------------
  describe('getThumbnail', () => {
    it('parses valid PNG data URL and returns buffer and mediaType', async () => {
      const pngBase64 = 'iVBORw0KGgo='; // minimal valid base64
      mockMaybeSingle.mockResolvedValue({
        data: {
          thumbnail_data_url: `data:image/png;base64,${pngBase64}`,
        },
        error: null,
      });

      const result = await getThumbnail('test-uuid');

      expect(result.mediaType).toBe('image/png');
      expect(result.data).toBeInstanceOf(Buffer);
      expect(result.data.toString('base64')).toBe(pngBase64);
    });

    it('parses valid JPEG data URL and returns correct mediaType', async () => {
      const jpegBase64 = '/9j/4AAQ';
      mockMaybeSingle.mockResolvedValue({
        data: {
          thumbnail_data_url: `data:image/jpeg;base64,${jpegBase64}`,
        },
        error: null,
      });

      const result = await getThumbnail('test-uuid');

      expect(result.mediaType).toBe('image/jpeg');
    });

    it('throws when paper not found', async () => {
      mockMaybeSingle.mockResolvedValue({ data: null, error: null });

      await expect(getThumbnail('nonexistent')).rejects.toThrow(
        'Paper not found: nonexistent'
      );
    });

    it('throws when paper has no thumbnail', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: {
          thumbnail_data_url: null,
        },
        error: null,
      });

      await expect(getThumbnail('test-uuid')).rejects.toThrow(
        'Paper has no thumbnail: test-uuid'
      );
    });

    it('throws when data URL format is invalid (missing data: prefix)', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: {
          thumbnail_data_url: 'image/png;base64,abc123',
        },
        error: null,
      });

      await expect(getThumbnail('test-uuid')).rejects.toThrow(
        'Invalid thumbnail data URL format for paper: test-uuid'
      );
    });

    it('throws when data URL format is invalid (missing base64)', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: {
          thumbnail_data_url: 'data:image/png,abc123',
        },
        error: null,
      });

      await expect(getThumbnail('test-uuid')).rejects.toThrow(
        'Invalid thumbnail data URL format for paper: test-uuid'
      );
    });
  });

  // --------------------------------------------------------------------------
  // getPaperSummary - Summary extraction from processedContent
  // --------------------------------------------------------------------------
  describe('getPaperSummary', () => {
    it('extracts five_minute_summary from processedContent', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: {
          paper_uuid: 'test-uuid',
          title: 'Test Paper',
          authors: 'John Doe',
          arxiv_url: 'https://arxiv.org/abs/2301.12345',
          processed_content: JSON.stringify({
            five_minute_summary: 'This is a summary.',
          }),
          num_pages: 10,
        },
        error: null,
      });

      const result = await getPaperSummary('test-uuid');

      expect(result.fiveMinuteSummary).toBe('This is a summary.');
      expect(result.paperId).toBe('test-uuid');
      expect(result.title).toBe('Test Paper');
      expect(result.pageCount).toBe(10);
      expect(result.thumbnailUrl).toBe('/api/papers/thumbnails/test-uuid');
    });

    it('returns null fiveMinuteSummary when processedContent is null', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: {
          paper_uuid: 'test-uuid',
          title: 'Test Paper',
          authors: null,
          arxiv_url: null,
          processed_content: null,
          num_pages: null,
        },
        error: null,
      });

      const result = await getPaperSummary('test-uuid');

      expect(result.fiveMinuteSummary).toBeNull();
      expect(result.pageCount).toBe(0);
    });

    it('returns null fiveMinuteSummary when processedContent has invalid JSON', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: {
          paper_uuid: 'test-uuid',
          title: 'Test Paper',
          authors: null,
          arxiv_url: null,
          processed_content: 'not valid json {{{',
          num_pages: 5,
        },
        error: null,
      });

      const result = await getPaperSummary('test-uuid');

      expect(result.fiveMinuteSummary).toBeNull();
    });

    it('returns null fiveMinuteSummary when five_minute_summary field is missing', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: {
          paper_uuid: 'test-uuid',
          title: 'Test Paper',
          authors: null,
          arxiv_url: null,
          processed_content: JSON.stringify({ other_field: 'value' }),
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
  // getPaperMarkdown - Markdown extraction from processedContent
  // --------------------------------------------------------------------------
  describe('getPaperMarkdown', () => {
    it('returns final_markdown from valid processedContent', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: {
          processed_content: JSON.stringify({
            final_markdown: '# Paper Title\n\nContent here.',
          }),
        },
        error: null,
      });

      const result = await getPaperMarkdown('test-uuid');

      expect(result).toBe('# Paper Title\n\nContent here.');
    });

    it('returns empty string when final_markdown is not present', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: {
          processed_content: JSON.stringify({ other_field: 'value' }),
        },
        error: null,
      });

      const result = await getPaperMarkdown('test-uuid');

      expect(result).toBe('');
    });

    it('throws when paper not found', async () => {
      mockMaybeSingle.mockResolvedValue({ data: null, error: null });

      await expect(getPaperMarkdown('nonexistent')).rejects.toThrow(
        'Paper not found: nonexistent'
      );
    });

    it('throws when paper has no processedContent', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: {
          processed_content: null,
        },
        error: null,
      });

      await expect(getPaperMarkdown('test-uuid')).rejects.toThrow(
        'Paper has no processed content: test-uuid'
      );
    });

    it('throws when processedContent has invalid JSON', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: {
          processed_content: 'not valid json {{{',
        },
        error: null,
      });

      await expect(getPaperMarkdown('test-uuid')).rejects.toThrow(
        'Failed to parse processed content for paper: test-uuid'
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
            { paper_uuid: 'uuid-1', title: 'Paper 1', authors: 'Author 1', thumbnail_data_url: null },
            { paper_uuid: 'uuid-2', title: 'Paper 2', authors: 'Author 2', thumbnail_data_url: 'data:image/png;base64,abc' },
            { paper_uuid: 'uuid-3', title: 'Paper 3', authors: 'Author 3', thumbnail_data_url: null }, // extra item
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
          data: [{ paper_uuid: 'uuid-1', title: 'Paper 1', authors: null, thumbnail_data_url: null }],
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
          data: [{ paper_uuid: 'uuid-1', title: 'Paper 1', authors: null, thumbnail_data_url: null }],
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
          data: [{ paper_uuid: 'uuid-1', title: 'Paper', authors: null, thumbnail_data_url: null }],
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
          thumbnail_data_url: null,
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
          thumbnail_data_url: null,
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
          thumbnail_data_url: null,
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
