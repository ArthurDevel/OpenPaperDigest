/**
 * Unit tests for arXiv API client utilities.
 * Tests normalizeId, buildPdfUrl, and fetchMetadata functions.
 *
 * @vitest-environment jsdom
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { normalizeId, buildPdfUrl, fetchMetadata } from './arxiv';

// ============================================================================
// NORMALZE ID TESTS
// ============================================================================

describe('arxiv', () => {
  describe('normalizeId', () => {
    it('parses new-style ID without version', () => {
      const result = normalizeId('2301.12345');
      expect(result).toEqual({ arxivId: '2301.12345', version: null });
    });

    it('parses new-style ID with version', () => {
      const result = normalizeId('2301.12345v2');
      expect(result).toEqual({ arxivId: '2301.12345', version: 'v2' });
    });

    it('parses old-style ID without version', () => {
      const result = normalizeId('hep-th/9901001');
      expect(result).toEqual({ arxivId: 'hep-th/9901001', version: null });
    });

    it('parses old-style ID with version', () => {
      const result = normalizeId('hep-th/9901001v2');
      expect(result).toEqual({ arxivId: 'hep-th/9901001', version: 'v2' });
    });

    it('parses arXiv prefix format', () => {
      const result = normalizeId('arXiv:2301.12345');
      expect(result).toEqual({ arxivId: '2301.12345', version: null });
    });

    it('parses full abs URL', () => {
      const result = normalizeId('https://arxiv.org/abs/2301.12345');
      expect(result).toEqual({ arxivId: '2301.12345', version: null });
    });

    it('parses full abs URL with version', () => {
      const result = normalizeId('https://arxiv.org/abs/2301.12345v1');
      expect(result).toEqual({ arxivId: '2301.12345', version: 'v1' });
    });

    it('parses full PDF URL', () => {
      const result = normalizeId('https://arxiv.org/pdf/2301.12345.pdf');
      expect(result).toEqual({ arxivId: '2301.12345', version: null });
    });

    it('throws error for invalid input', () => {
      expect(() => normalizeId('invalid-string')).toThrow();
    });
  });

  // ============================================================================
  // BUILD PDF URL TESTS
  // ============================================================================

  describe('buildPdfUrl', () => {
    it('builds URL without version', () => {
      const result = buildPdfUrl('2301.12345');
      expect(result).toBe('https://arxiv.org/pdf/2301.12345.pdf');
    });

    it('builds URL with version', () => {
      const result = buildPdfUrl('2301.12345', 'v2');
      expect(result).toBe('https://arxiv.org/pdf/2301.12345v2.pdf');
    });

    it('builds URL with null version', () => {
      const result = buildPdfUrl('2301.12345', null);
      expect(result).toBe('https://arxiv.org/pdf/2301.12345.pdf');
    });
  });

  // ============================================================================
  // FETCH METADATA TESTS
  // ============================================================================

  describe('fetchMetadata', () => {
    const originalFetch = global.fetch;

    beforeEach(() => {
      vi.resetAllMocks();
    });

    afterEach(() => {
      global.fetch = originalFetch;
    });

    it('parses valid Atom XML response', async () => {
      const mockXml = `<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Test Paper Title</title>
    <summary>This is the abstract of the test paper.</summary>
    <published>2023-01-15T00:00:00Z</published>
    <author>
      <name>John Doe</name>
    </author>
    <author>
      <name>Jane Smith</name>
    </author>
    <category term="cs.AI" />
    <category term="cs.LG" />
  </entry>
</feed>`;

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        text: () => Promise.resolve(mockXml),
      });

      const result = await fetchMetadata('2301.12345');

      expect(result.arxivId).toBe('2301.12345');
      expect(result.title).toBe('Test Paper Title');
      expect(result.abstract).toBe('This is the abstract of the test paper.');
      expect(result.authors).toEqual(['John Doe', 'Jane Smith']);
      expect(result.categories).toEqual(['cs.AI', 'cs.LG']);
      expect(result.publishedAt).toEqual(new Date('2023-01-15T00:00:00Z'));
    });

    it('throws error on 404 response', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        statusText: 'Not Found',
      });

      await expect(fetchMetadata('nonexistent')).rejects.toThrow(
        'arXiv API request failed: 404 Not Found'
      );
    });

    it('throws error when no entry found in response', async () => {
      const mockXml = `<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
</feed>`;

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        text: () => Promise.resolve(mockXml),
      });

      await expect(fetchMetadata('2301.12345')).rejects.toThrow(
        'No metadata found for arXiv ID: 2301.12345'
      );
    });
  });
});
