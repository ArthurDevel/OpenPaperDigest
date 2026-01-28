/**
 * Unit tests for slugs.service.ts
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { buildPaperSlug, resolveSlug, getSlugForPaper, createSlug } from './slugs.service';

// Mock Prisma
vi.mock('@/lib/db', () => ({
  prisma: {
    paperSlug: {
      findUnique: vi.fn(),
      findFirst: vi.fn(),
      create: vi.fn(),
    },
    paper: {
      findUnique: vi.fn(),
    },
  },
}));

import { prisma } from '@/lib/db';

const mockedPrisma = prisma as {
  paperSlug: {
    findUnique: ReturnType<typeof vi.fn>;
    findFirst: ReturnType<typeof vi.fn>;
    create: ReturnType<typeof vi.fn>;
  };
  paper: {
    findUnique: ReturnType<typeof vi.fn>;
  };
};

// ============================================================================
// TESTS
// ============================================================================

describe('slugs.service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // --------------------------------------------------------------------------
  // buildPaperSlug - Pure logic tests
  // --------------------------------------------------------------------------
  describe('buildPaperSlug', () => {
    it('generates slug from title and first author last name', () => {
      const result = buildPaperSlug('Deep Learning for NLP', 'John Smith, Jane Doe');
      expect(result).toBe('deep-learning-for-nlp-smith');
    });

    it('returns untitled-author when title is null', () => {
      const result = buildPaperSlug(null, 'John Smith');
      expect(result).toBe('untitled-smith');
    });

    it('returns title-only slug when authors is null', () => {
      const result = buildPaperSlug('Deep Learning', null);
      expect(result).toBe('deep-learning');
    });

    it('returns untitled when both title and authors are null', () => {
      const result = buildPaperSlug(null, null);
      expect(result).toBe('untitled');
    });

    it('removes special characters from title', () => {
      const result = buildPaperSlug('GPT-4: A New Era!', 'OpenAI Team');
      expect(result).toBe('gpt-4-a-new-era-team');
    });

    it('collapses multiple spaces into single hyphen', () => {
      const result = buildPaperSlug('Deep   Learning', 'John Smith');
      expect(result).toBe('deep-learning-smith');
    });

    it('truncates long slugs to MAX_SLUG_LENGTH (200)', () => {
      const longTitle = 'a'.repeat(250);
      const result = buildPaperSlug(longTitle, 'Smith');
      expect(result.length).toBeLessThanOrEqual(200);
    });

    it('removes trailing hyphen after truncation', () => {
      // Create a title that when combined with author will be truncated at a hyphen
      const title = 'a'.repeat(195) + ' word';
      const result = buildPaperSlug(title, 'Smith');
      expect(result.endsWith('-')).toBe(false);
    });

    it('trims leading and trailing spaces from title', () => {
      const result = buildPaperSlug('  Deep Learning  ', 'Smith');
      expect(result).toBe('deep-learning-smith');
    });

    it('uses last word of first author name as last name', () => {
      const result = buildPaperSlug('Test', 'John Paul Smith Jr.');
      expect(result).toBe('test-jr');
    });

    it('handles empty authors string', () => {
      const result = buildPaperSlug('Test Paper', '');
      expect(result).toBe('test-paper');
    });

    it('handles author with only spaces', () => {
      const result = buildPaperSlug('Test Paper', '   ');
      expect(result).toBe('test-paper');
    });
  });

  // --------------------------------------------------------------------------
  // resolveSlug - Database tests with mocked Prisma
  // --------------------------------------------------------------------------
  describe('resolveSlug', () => {
    it('returns null paperUuid when slug not found', async () => {
      mockedPrisma.paperSlug.findUnique.mockResolvedValue(null);

      const result = await resolveSlug('test-slug');

      expect(result).toEqual({
        paperUuid: null,
        slug: 'test-slug',
        tombstone: false,
      });
      expect(mockedPrisma.paperSlug.findUnique).toHaveBeenCalledWith({
        where: { slug: 'test-slug' },
        select: { slug: true, paperUuid: true, tombstone: true },
      });
    });

    it('returns slug data when found', async () => {
      mockedPrisma.paperSlug.findUnique.mockResolvedValue({
        slug: 'test-slug',
        paperUuid: 'uuid-123',
        tombstone: false,
      });

      const result = await resolveSlug('test-slug');

      expect(result).toEqual({
        paperUuid: 'uuid-123',
        slug: 'test-slug',
        tombstone: false,
      });
    });

    it('returns tombstone status when slug is tombstoned', async () => {
      mockedPrisma.paperSlug.findUnique.mockResolvedValue({
        slug: 'old-slug',
        paperUuid: 'uuid-123',
        tombstone: true,
      });

      const result = await resolveSlug('old-slug');

      expect(result.tombstone).toBe(true);
    });
  });

  // --------------------------------------------------------------------------
  // getSlugForPaper - Database tests with mocked Prisma
  // --------------------------------------------------------------------------
  describe('getSlugForPaper', () => {
    it('returns null paperUuid when no active slug exists', async () => {
      mockedPrisma.paperSlug.findFirst.mockResolvedValue(null);

      const result = await getSlugForPaper('uuid-123');

      expect(result).toEqual({
        paperUuid: null,
        slug: '',
        tombstone: false,
      });
      expect(mockedPrisma.paperSlug.findFirst).toHaveBeenCalledWith({
        where: { paperUuid: 'uuid-123', tombstone: false },
        orderBy: { createdAt: 'desc' },
        select: { slug: true, paperUuid: true, tombstone: true },
      });
    });

    it('returns slug data when active slug found', async () => {
      mockedPrisma.paperSlug.findFirst.mockResolvedValue({
        slug: 'paper-slug',
        paperUuid: 'uuid-123',
        tombstone: false,
      });

      const result = await getSlugForPaper('uuid-123');

      expect(result).toEqual({
        paperUuid: 'uuid-123',
        slug: 'paper-slug',
        tombstone: false,
      });
    });
  });

  // --------------------------------------------------------------------------
  // createSlug - Database tests with mocked Prisma
  // --------------------------------------------------------------------------
  describe('createSlug', () => {
    it('returns existing slug without creating new one', async () => {
      mockedPrisma.paperSlug.findFirst.mockResolvedValue({
        slug: 'existing-slug',
        paperUuid: 'uuid-123',
        tombstone: false,
      });

      const result = await createSlug('uuid-123');

      expect(result).toEqual({
        paperUuid: 'uuid-123',
        slug: 'existing-slug',
        tombstone: false,
      });
      expect(mockedPrisma.paper.findUnique).not.toHaveBeenCalled();
      expect(mockedPrisma.paperSlug.create).not.toHaveBeenCalled();
    });

    it('throws error when paper not found', async () => {
      mockedPrisma.paperSlug.findFirst.mockResolvedValue(null);
      mockedPrisma.paper.findUnique.mockResolvedValue(null);

      await expect(createSlug('nonexistent-uuid')).rejects.toThrow(
        'Paper not found: nonexistent-uuid'
      );
    });

    it('creates new slug when none exists', async () => {
      mockedPrisma.paperSlug.findFirst.mockResolvedValue(null);
      mockedPrisma.paper.findUnique.mockResolvedValue({
        title: 'Test Paper',
        authors: 'John Smith',
      });
      mockedPrisma.paperSlug.findUnique.mockResolvedValue(null);
      mockedPrisma.paperSlug.create.mockResolvedValue({
        slug: 'test-paper-smith',
        paperUuid: 'uuid-123',
        tombstone: false,
      });

      const result = await createSlug('uuid-123');

      expect(result).toEqual({
        paperUuid: 'uuid-123',
        slug: 'test-paper-smith',
        tombstone: false,
      });
      expect(mockedPrisma.paperSlug.create).toHaveBeenCalledWith({
        data: {
          slug: 'test-paper-smith',
          paperUuid: 'uuid-123',
          tombstone: false,
        },
      });
    });

    it('appends UUID suffix when slug collision with different paper', async () => {
      mockedPrisma.paperSlug.findFirst.mockResolvedValue(null);
      mockedPrisma.paper.findUnique.mockResolvedValue({
        title: 'Test Paper',
        authors: 'John Smith',
      });
      mockedPrisma.paperSlug.findUnique.mockResolvedValue({
        slug: 'test-paper-smith',
        paperUuid: 'other-uuid',
        tombstone: false,
      });
      mockedPrisma.paperSlug.create.mockResolvedValue({
        slug: 'test-paper-smith-uuid-123',
        paperUuid: 'uuid-12345678-abcd',
        tombstone: false,
      });

      const result = await createSlug('uuid-12345678-abcd');

      expect(mockedPrisma.paperSlug.create).toHaveBeenCalledWith({
        data: {
          slug: 'test-paper-smith-uuid-123',
          paperUuid: 'uuid-12345678-abcd',
          tombstone: false,
        },
      });
      expect(result.slug).toBe('test-paper-smith-uuid-123');
    });

    it('returns existing slug when collision is with same paper and active', async () => {
      mockedPrisma.paperSlug.findFirst.mockResolvedValue(null);
      mockedPrisma.paper.findUnique.mockResolvedValue({
        title: 'Test Paper',
        authors: 'John Smith',
      });
      mockedPrisma.paperSlug.findUnique.mockResolvedValue({
        slug: 'test-paper-smith',
        paperUuid: 'uuid-123',
        tombstone: false,
      });

      const result = await createSlug('uuid-123');

      expect(result).toEqual({
        paperUuid: 'uuid-123',
        slug: 'test-paper-smith',
        tombstone: false,
      });
      expect(mockedPrisma.paperSlug.create).not.toHaveBeenCalled();
    });

    it('creates new slug with suffix when existing slug is tombstoned', async () => {
      mockedPrisma.paperSlug.findFirst.mockResolvedValue(null);
      mockedPrisma.paper.findUnique.mockResolvedValue({
        title: 'Test Paper',
        authors: 'John Smith',
      });
      mockedPrisma.paperSlug.findUnique.mockResolvedValue({
        slug: 'test-paper-smith',
        paperUuid: 'uuid-123',
        tombstone: true,
      });
      mockedPrisma.paperSlug.create.mockResolvedValue({
        slug: 'test-paper-smith-uuid-123',
        paperUuid: 'uuid-12345678',
        tombstone: false,
      });

      const result = await createSlug('uuid-12345678');

      expect(mockedPrisma.paperSlug.create).toHaveBeenCalled();
    });
  });
});
