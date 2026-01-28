/**
 * Unit tests for papers.service.ts
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the db module
vi.mock('@/lib/db', () => ({
  prisma: {
    paper: {
      findUnique: vi.fn(),
      findMany: vi.fn(),
      count: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
    },
  },
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

import { prisma } from '@/lib/db';
import {
  getThumbnail,
  getPaperSummary,
  getPaperMarkdown,
  checkArxivExists,
  enqueueArxiv,
  listMinimalPapers,
  restartPaper,
} from './papers.service';

const mockedPrisma = prisma as {
  paper: {
    findUnique: ReturnType<typeof vi.fn>;
    findMany: ReturnType<typeof vi.fn>;
    count: ReturnType<typeof vi.fn>;
    create: ReturnType<typeof vi.fn>;
    update: ReturnType<typeof vi.fn>;
  };
};

// ============================================================================
// TESTS
// ============================================================================

describe('papers.service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // --------------------------------------------------------------------------
  // getThumbnail - Base64 data URL parsing
  // --------------------------------------------------------------------------
  describe('getThumbnail', () => {
    it('parses valid PNG data URL and returns buffer and mediaType', async () => {
      const pngBase64 = 'iVBORw0KGgo='; // minimal valid base64
      mockedPrisma.paper.findUnique.mockResolvedValue({
        thumbnailDataUrl: `data:image/png;base64,${pngBase64}`,
      });

      const result = await getThumbnail('test-uuid');

      expect(result.mediaType).toBe('image/png');
      expect(result.data).toBeInstanceOf(Buffer);
      expect(result.data.toString('base64')).toBe(pngBase64);
    });

    it('parses valid JPEG data URL and returns correct mediaType', async () => {
      const jpegBase64 = '/9j/4AAQ';
      mockedPrisma.paper.findUnique.mockResolvedValue({
        thumbnailDataUrl: `data:image/jpeg;base64,${jpegBase64}`,
      });

      const result = await getThumbnail('test-uuid');

      expect(result.mediaType).toBe('image/jpeg');
    });

    it('throws when paper not found', async () => {
      mockedPrisma.paper.findUnique.mockResolvedValue(null);

      await expect(getThumbnail('nonexistent')).rejects.toThrow(
        'Paper not found: nonexistent'
      );
    });

    it('throws when paper has no thumbnail', async () => {
      mockedPrisma.paper.findUnique.mockResolvedValue({
        thumbnailDataUrl: null,
      });

      await expect(getThumbnail('test-uuid')).rejects.toThrow(
        'Paper has no thumbnail: test-uuid'
      );
    });

    it('throws when data URL format is invalid (missing data: prefix)', async () => {
      mockedPrisma.paper.findUnique.mockResolvedValue({
        thumbnailDataUrl: 'image/png;base64,abc123',
      });

      await expect(getThumbnail('test-uuid')).rejects.toThrow(
        'Invalid thumbnail data URL format for paper: test-uuid'
      );
    });

    it('throws when data URL format is invalid (missing base64)', async () => {
      mockedPrisma.paper.findUnique.mockResolvedValue({
        thumbnailDataUrl: 'data:image/png,abc123',
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
      mockedPrisma.paper.findUnique.mockResolvedValue({
        paperUuid: 'test-uuid',
        title: 'Test Paper',
        authors: 'John Doe',
        arxivUrl: 'https://arxiv.org/abs/2301.12345',
        processedContent: JSON.stringify({
          five_minute_summary: 'This is a summary.',
        }),
        numPages: 10,
      });

      const result = await getPaperSummary('test-uuid');

      expect(result.fiveMinuteSummary).toBe('This is a summary.');
      expect(result.paperId).toBe('test-uuid');
      expect(result.title).toBe('Test Paper');
      expect(result.pageCount).toBe(10);
      expect(result.thumbnailUrl).toBe('/api/papers/thumbnails/test-uuid');
    });

    it('returns null fiveMinuteSummary when processedContent is null', async () => {
      mockedPrisma.paper.findUnique.mockResolvedValue({
        paperUuid: 'test-uuid',
        title: 'Test Paper',
        authors: null,
        arxivUrl: null,
        processedContent: null,
        numPages: null,
      });

      const result = await getPaperSummary('test-uuid');

      expect(result.fiveMinuteSummary).toBeNull();
      expect(result.pageCount).toBe(0);
    });

    it('returns null fiveMinuteSummary when processedContent has invalid JSON', async () => {
      mockedPrisma.paper.findUnique.mockResolvedValue({
        paperUuid: 'test-uuid',
        title: 'Test Paper',
        authors: null,
        arxivUrl: null,
        processedContent: 'not valid json {{{',
        numPages: 5,
      });

      const result = await getPaperSummary('test-uuid');

      expect(result.fiveMinuteSummary).toBeNull();
    });

    it('returns null fiveMinuteSummary when five_minute_summary field is missing', async () => {
      mockedPrisma.paper.findUnique.mockResolvedValue({
        paperUuid: 'test-uuid',
        title: 'Test Paper',
        authors: null,
        arxivUrl: null,
        processedContent: JSON.stringify({ other_field: 'value' }),
        numPages: 5,
      });

      const result = await getPaperSummary('test-uuid');

      expect(result.fiveMinuteSummary).toBeNull();
    });

    it('throws when paper not found', async () => {
      mockedPrisma.paper.findUnique.mockResolvedValue(null);

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
      mockedPrisma.paper.findUnique.mockResolvedValue({
        processedContent: JSON.stringify({
          final_markdown: '# Paper Title\n\nContent here.',
        }),
      });

      const result = await getPaperMarkdown('test-uuid');

      expect(result).toBe('# Paper Title\n\nContent here.');
    });

    it('returns empty string when final_markdown is not present', async () => {
      mockedPrisma.paper.findUnique.mockResolvedValue({
        processedContent: JSON.stringify({ other_field: 'value' }),
      });

      const result = await getPaperMarkdown('test-uuid');

      expect(result).toBe('');
    });

    it('throws when paper not found', async () => {
      mockedPrisma.paper.findUnique.mockResolvedValue(null);

      await expect(getPaperMarkdown('nonexistent')).rejects.toThrow(
        'Paper not found: nonexistent'
      );
    });

    it('throws when paper has no processedContent', async () => {
      mockedPrisma.paper.findUnique.mockResolvedValue({
        processedContent: null,
      });

      await expect(getPaperMarkdown('test-uuid')).rejects.toThrow(
        'Paper has no processed content: test-uuid'
      );
    });

    it('throws when processedContent has invalid JSON', async () => {
      mockedPrisma.paper.findUnique.mockResolvedValue({
        processedContent: 'not valid json {{{',
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
      mockedPrisma.paper.findUnique.mockResolvedValue({
        paperUuid: 'test-uuid',
        status: 'completed',
        slugs: [{ slug: 'test-paper-slug' }],
      });

      const result = await checkArxivExists('2301.12345');

      expect(result.exists).toBe(true);
      expect(result.viewerUrl).toBe('/paper/test-paper-slug');
    });

    it('returns exists: true with uuid-based viewerUrl when paper completed without slug', async () => {
      mockedPrisma.paper.findUnique.mockResolvedValue({
        paperUuid: 'test-uuid',
        status: 'completed',
        slugs: [],
      });

      const result = await checkArxivExists('2301.12345');

      expect(result.exists).toBe(true);
      expect(result.viewerUrl).toBe('/paper/test-uuid');
    });

    it('returns exists: false when paper is not completed', async () => {
      mockedPrisma.paper.findUnique.mockResolvedValue({
        paperUuid: 'test-uuid',
        status: 'processing',
        slugs: [],
      });

      const result = await checkArxivExists('2301.12345');

      expect(result.exists).toBe(false);
      expect(result.viewerUrl).toBeNull();
    });

    it('returns exists: false when paper not found', async () => {
      mockedPrisma.paper.findUnique.mockResolvedValue(null);

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
      mockedPrisma.paper.findUnique.mockResolvedValue({
        id: BigInt(42),
        paperUuid: 'existing-uuid',
        status: 'completed',
      });

      const result = await enqueueArxiv('https://arxiv.org/abs/2301.12345');

      expect(result).toEqual({
        jobDbId: 42,
        paperUuid: 'existing-uuid',
        status: 'completed',
      });
      expect(mockedPrisma.paper.create).not.toHaveBeenCalled();
    });

    it('creates new paper record when paper does not exist', async () => {
      mockedPrisma.paper.findUnique.mockResolvedValue(null);
      mockedPrisma.paper.create.mockResolvedValue({
        id: BigInt(99),
        paperUuid: 'mock-uuid-1234',
        status: 'not_started',
      });

      const result = await enqueueArxiv('https://arxiv.org/abs/2301.12345');

      expect(result).toEqual({
        jobDbId: 99,
        paperUuid: 'mock-uuid-1234',
        status: 'not_started',
      });
      expect(mockedPrisma.paper.create).toHaveBeenCalledWith({
        data: {
          paperUuid: 'mock-uuid-1234',
          arxivId: '2301.12345',
          arxivVersion: null,
          arxivUrl: 'https://arxiv.org/abs/2301.12345',
          status: 'not_started',
        },
      });
    });

    it('includes version in arxivUrl when version is present', async () => {
      mockedPrisma.paper.findUnique.mockResolvedValue(null);
      mockedPrisma.paper.create.mockResolvedValue({
        id: BigInt(99),
        paperUuid: 'mock-uuid-1234',
        status: 'not_started',
      });

      await enqueueArxiv('https://arxiv.org/abs/2302.99999v2');

      expect(mockedPrisma.paper.create).toHaveBeenCalledWith({
        data: expect.objectContaining({
          arxivId: '2302.99999',
          arxivVersion: 'v2',
          arxivUrl: 'https://arxiv.org/abs/2302.99999v2',
        }),
      });
    });
  });

  // --------------------------------------------------------------------------
  // listMinimalPapers - Paginated paper list
  // --------------------------------------------------------------------------
  describe('listMinimalPapers', () => {
    it('returns paginated list with hasMore correctly calculated', async () => {
      mockedPrisma.paper.findMany.mockResolvedValue([
        {
          paperUuid: 'uuid-1',
          title: 'Paper 1',
          authors: 'Author 1',
          thumbnailDataUrl: null,
          slugs: [{ slug: 'paper-1-slug' }],
        },
        {
          paperUuid: 'uuid-2',
          title: 'Paper 2',
          authors: 'Author 2',
          thumbnailDataUrl: 'data:image/png;base64,abc',
          slugs: [],
        },
      ]);
      mockedPrisma.paper.count.mockResolvedValue(5);

      const result = await listMinimalPapers(1, 2);

      expect(result.items).toHaveLength(2);
      expect(result.total).toBe(5);
      expect(result.page).toBe(1);
      expect(result.limit).toBe(2);
      expect(result.hasMore).toBe(true);
    });

    it('defaults to page 1 and limit 20', async () => {
      mockedPrisma.paper.findMany.mockResolvedValue([]);
      mockedPrisma.paper.count.mockResolvedValue(0);

      const result = await listMinimalPapers();

      expect(result.page).toBe(1);
      expect(result.limit).toBe(20);
      expect(mockedPrisma.paper.findMany).toHaveBeenCalledWith(
        expect.objectContaining({
          skip: 0,
          take: 20,
        })
      );
    });

    it('maps slug correctly from nested relation', async () => {
      mockedPrisma.paper.findMany.mockResolvedValue([
        {
          paperUuid: 'uuid-1',
          title: 'Paper 1',
          authors: null,
          thumbnailDataUrl: null,
          slugs: [{ slug: 'my-paper-slug' }],
        },
      ]);
      mockedPrisma.paper.count.mockResolvedValue(1);

      const result = await listMinimalPapers(1, 10);

      expect(result.items[0].slug).toBe('my-paper-slug');
    });

    it('sets slug to null when no slugs exist', async () => {
      mockedPrisma.paper.findMany.mockResolvedValue([
        {
          paperUuid: 'uuid-1',
          title: 'Paper 1',
          authors: null,
          thumbnailDataUrl: null,
          slugs: [],
        },
      ]);
      mockedPrisma.paper.count.mockResolvedValue(1);

      const result = await listMinimalPapers(1, 10);

      expect(result.items[0].slug).toBeNull();
    });

    it('calculates hasMore as false when on last page', async () => {
      mockedPrisma.paper.findMany.mockResolvedValue([
        {
          paperUuid: 'uuid-1',
          title: 'Paper',
          authors: null,
          thumbnailDataUrl: null,
          slugs: [],
        },
      ]);
      mockedPrisma.paper.count.mockResolvedValue(3);

      const result = await listMinimalPapers(2, 2);

      // skip = (2-1) * 2 = 2, returned 1 item, 2 + 1 = 3 which equals total
      expect(result.hasMore).toBe(false);
    });
  });

  // --------------------------------------------------------------------------
  // restartPaper - Reset paper status for reprocessing
  // --------------------------------------------------------------------------
  describe('restartPaper', () => {
    it('resets paper status to not_started when paper found and not processing', async () => {
      const now = new Date();
      mockedPrisma.paper.findUnique.mockResolvedValue({
        id: BigInt(1),
        status: 'failed',
      });
      mockedPrisma.paper.update.mockResolvedValue({
        paperUuid: 'test-uuid',
        status: 'not_started',
        errorMessage: null,
        createdAt: now,
        updatedAt: now,
        startedAt: null,
        finishedAt: null,
        arxivId: '2301.12345',
        arxivVersion: null,
        arxivUrl: 'https://arxiv.org/abs/2301.12345',
        title: 'Test Paper',
        authors: 'Author',
        numPages: 10,
        thumbnailDataUrl: null,
        processingTimeSeconds: null,
        totalCost: null,
        avgCostPerPage: null,
      });

      const result = await restartPaper('test-uuid');

      expect(result.status).toBe('not_started');
      expect(result.errorMessage).toBeNull();
      expect(mockedPrisma.paper.update).toHaveBeenCalledWith({
        where: { paperUuid: 'test-uuid' },
        data: expect.objectContaining({
          status: 'not_started',
          errorMessage: null,
          startedAt: null,
          finishedAt: null,
        }),
        select: expect.any(Object),
      });
    });

    it('throws when paper not found', async () => {
      mockedPrisma.paper.findUnique.mockResolvedValue(null);

      await expect(restartPaper('nonexistent')).rejects.toThrow(
        'Paper not found: nonexistent'
      );
    });

    it('throws when paper is already processing', async () => {
      mockedPrisma.paper.findUnique.mockResolvedValue({
        id: BigInt(1),
        status: 'processing',
      });

      await expect(restartPaper('test-uuid')).rejects.toThrow(
        'Paper is already processing'
      );
    });

    it('allows restart when paper status is completed', async () => {
      const now = new Date();
      mockedPrisma.paper.findUnique.mockResolvedValue({
        id: BigInt(1),
        status: 'completed',
      });
      mockedPrisma.paper.update.mockResolvedValue({
        paperUuid: 'test-uuid',
        status: 'not_started',
        errorMessage: null,
        createdAt: now,
        updatedAt: now,
        startedAt: null,
        finishedAt: null,
        arxivId: '2301.12345',
        arxivVersion: null,
        arxivUrl: 'https://arxiv.org/abs/2301.12345',
        title: 'Test Paper',
        authors: 'Author',
        numPages: 10,
        thumbnailDataUrl: null,
        processingTimeSeconds: null,
        totalCost: null,
        avgCostPerPage: null,
      });

      const result = await restartPaper('test-uuid');

      expect(result.status).toBe('not_started');
    });

    it('allows restart when paper status is not_started', async () => {
      const now = new Date();
      mockedPrisma.paper.findUnique.mockResolvedValue({
        id: BigInt(1),
        status: 'not_started',
      });
      mockedPrisma.paper.update.mockResolvedValue({
        paperUuid: 'test-uuid',
        status: 'not_started',
        errorMessage: null,
        createdAt: now,
        updatedAt: now,
        startedAt: null,
        finishedAt: null,
        arxivId: null,
        arxivVersion: null,
        arxivUrl: null,
        title: null,
        authors: null,
        numPages: null,
        thumbnailDataUrl: null,
        processingTimeSeconds: null,
        totalCost: null,
        avgCostPerPage: null,
      });

      const result = await restartPaper('test-uuid');

      expect(result.status).toBe('not_started');
    });
  });
});
