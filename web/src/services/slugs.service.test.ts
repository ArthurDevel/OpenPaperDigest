/**
 * Unit tests for slugs.service.ts
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

import { buildPaperSlug, resolveSlug, getSlugForPaper, createSlug } from './slugs.service';

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
  // resolveSlug - Database tests with mocked Supabase
  // --------------------------------------------------------------------------
  describe('resolveSlug', () => {
    it('returns null paperUuid when slug not found', async () => {
      mockMaybeSingle.mockResolvedValue({ data: null, error: null });

      const result = await resolveSlug('test-slug');

      expect(result).toEqual({
        paperUuid: null,
        slug: 'test-slug',
        tombstone: false,
      });
      expect(mockFrom).toHaveBeenCalledWith('paper_slugs');
      expect(mockSelect).toHaveBeenCalledWith('slug, paper_uuid, tombstone');
      expect(mockEq).toHaveBeenCalledWith('slug', 'test-slug');
    });

    it('returns slug data when found', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: {
          slug: 'test-slug',
          paper_uuid: 'uuid-123',
          tombstone: false,
        },
        error: null,
      });

      const result = await resolveSlug('test-slug');

      expect(result).toEqual({
        paperUuid: 'uuid-123',
        slug: 'test-slug',
        tombstone: false,
      });
    });

    it('returns tombstone status when slug is tombstoned', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: {
          slug: 'old-slug',
          paper_uuid: 'uuid-123',
          tombstone: true,
        },
        error: null,
      });

      const result = await resolveSlug('old-slug');

      expect(result.tombstone).toBe(true);
    });

    it('throws error when database error occurs', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: null,
        error: { message: 'Database error' },
      });

      await expect(resolveSlug('test-slug')).rejects.toThrow('Database error');
    });
  });

  // --------------------------------------------------------------------------
  // getSlugForPaper - Database tests with mocked Supabase
  // --------------------------------------------------------------------------
  describe('getSlugForPaper', () => {
    it('returns null paperUuid when no active slug exists', async () => {
      mockMaybeSingle.mockResolvedValue({ data: null, error: null });

      const result = await getSlugForPaper('uuid-123');

      expect(result).toEqual({
        paperUuid: null,
        slug: '',
        tombstone: false,
      });
      expect(mockFrom).toHaveBeenCalledWith('paper_slugs');
      expect(mockSelect).toHaveBeenCalledWith('slug, paper_uuid, tombstone');
      expect(mockEq).toHaveBeenCalledWith('paper_uuid', 'uuid-123');
      expect(mockEq).toHaveBeenCalledWith('tombstone', false);
      expect(mockOrder).toHaveBeenCalledWith('created_at', { ascending: false });
      expect(mockLimit).toHaveBeenCalledWith(1);
    });

    it('returns slug data when active slug found', async () => {
      mockMaybeSingle.mockResolvedValue({
        data: {
          slug: 'paper-slug',
          paper_uuid: 'uuid-123',
          tombstone: false,
        },
        error: null,
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
  // createSlug - Database tests with mocked Supabase
  // --------------------------------------------------------------------------
  describe('createSlug', () => {
    it('returns existing slug without creating new one', async () => {
      // First call: getSlugForPaper finds existing slug
      mockMaybeSingle.mockResolvedValueOnce({
        data: {
          slug: 'existing-slug',
          paper_uuid: 'uuid-123',
          tombstone: false,
        },
        error: null,
      });

      const result = await createSlug('uuid-123');

      expect(result).toEqual({
        paperUuid: 'uuid-123',
        slug: 'existing-slug',
        tombstone: false,
      });
      // Should not have called insert
      expect(mockInsert).not.toHaveBeenCalled();
    });

    it('throws error when paper not found', async () => {
      // First call: getSlugForPaper returns no slug
      mockMaybeSingle
        .mockResolvedValueOnce({ data: null, error: null })
        // Second call: paper lookup returns nothing
        .mockResolvedValueOnce({ data: null, error: null });

      await expect(createSlug('nonexistent-uuid')).rejects.toThrow(
        'Paper not found: nonexistent-uuid'
      );
    });

    it('creates new slug when none exists', async () => {
      // First call: getSlugForPaper returns no slug
      mockMaybeSingle
        .mockResolvedValueOnce({ data: null, error: null })
        // Second call: paper lookup returns paper data
        .mockResolvedValueOnce({
          data: { title: 'Test Paper', authors: 'John Smith' },
          error: null,
        })
        // Third call: check existing slug returns nothing
        .mockResolvedValueOnce({ data: null, error: null });

      // Fourth call: insert with single returns created slug
      mockSingle.mockResolvedValueOnce({
        data: {
          slug: 'test-paper-smith',
          paper_uuid: 'uuid-123',
          tombstone: false,
        },
        error: null,
      });

      const result = await createSlug('uuid-123');

      expect(result).toEqual({
        paperUuid: 'uuid-123',
        slug: 'test-paper-smith',
        tombstone: false,
      });
      expect(mockInsert).toHaveBeenCalledWith(
        expect.objectContaining({
          slug: 'test-paper-smith',
          paper_uuid: 'uuid-123',
          tombstone: false,
        })
      );
    });

    it('appends UUID suffix when slug collision with different paper', async () => {
      // First call: getSlugForPaper returns no slug
      mockMaybeSingle
        .mockResolvedValueOnce({ data: null, error: null })
        // Second call: paper lookup returns paper data
        .mockResolvedValueOnce({
          data: { title: 'Test Paper', authors: 'John Smith' },
          error: null,
        })
        // Third call: check existing slug returns collision with different paper
        .mockResolvedValueOnce({
          data: {
            slug: 'test-paper-smith',
            paper_uuid: 'other-uuid',
            tombstone: false,
          },
          error: null,
        });

      // Fourth call: insert with single returns created slug with suffix
      mockSingle.mockResolvedValueOnce({
        data: {
          slug: 'test-paper-smith-uuid-123',
          paper_uuid: 'uuid-12345678-abcd',
          tombstone: false,
        },
        error: null,
      });

      const result = await createSlug('uuid-12345678-abcd');

      expect(mockInsert).toHaveBeenCalledWith(
        expect.objectContaining({
          slug: 'test-paper-smith-uuid-123',
          paper_uuid: 'uuid-12345678-abcd',
          tombstone: false,
        })
      );
      expect(result.slug).toBe('test-paper-smith-uuid-123');
    });

    it('returns existing slug when collision is with same paper and active', async () => {
      // First call: getSlugForPaper returns no slug
      mockMaybeSingle
        .mockResolvedValueOnce({ data: null, error: null })
        // Second call: paper lookup returns paper data
        .mockResolvedValueOnce({
          data: { title: 'Test Paper', authors: 'John Smith' },
          error: null,
        })
        // Third call: check existing slug returns same paper, active
        .mockResolvedValueOnce({
          data: {
            slug: 'test-paper-smith',
            paper_uuid: 'uuid-123',
            tombstone: false,
          },
          error: null,
        });

      const result = await createSlug('uuid-123');

      expect(result).toEqual({
        paperUuid: 'uuid-123',
        slug: 'test-paper-smith',
        tombstone: false,
      });
      expect(mockInsert).not.toHaveBeenCalled();
    });

    it('creates new slug with suffix when existing slug is tombstoned', async () => {
      // First call: getSlugForPaper returns no slug
      mockMaybeSingle
        .mockResolvedValueOnce({ data: null, error: null })
        // Second call: paper lookup returns paper data
        .mockResolvedValueOnce({
          data: { title: 'Test Paper', authors: 'John Smith' },
          error: null,
        })
        // Third call: check existing slug returns tombstoned
        .mockResolvedValueOnce({
          data: {
            slug: 'test-paper-smith',
            paper_uuid: 'uuid-123',
            tombstone: true,
          },
          error: null,
        });

      // Fourth call: insert with single returns created slug
      mockSingle.mockResolvedValueOnce({
        data: {
          slug: 'test-paper-smith-uuid-123',
          paper_uuid: 'uuid-12345678',
          tombstone: false,
        },
        error: null,
      });

      const result = await createSlug('uuid-12345678');

      expect(mockInsert).toHaveBeenCalled();
    });
  });
});
