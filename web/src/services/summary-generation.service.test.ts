/**
 * Unit tests for summary-generation.service.ts
 *
 * Tests the on-demand summary generation flow:
 * - URL-based PDF success path
 * - Base64 fallback when URL fails
 * - Error propagation when both paths fail
 * - Early return when summary already exists
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// ============================================================================
// MOCK SETUP
// ============================================================================

const {
  mockSingle,
  mockEq,
  mockSelect,
  mockFrom,
  mockRpc,
  mockChatCompletion,
  mockDownloadPdfAsBase64,
} = vi.hoisted(() => {
  const mockSingle = vi.fn();
  const mockEq = vi.fn();
  const mockSelect = vi.fn();
  const mockFrom = vi.fn();
  const mockRpc = vi.fn();
  const mockChatCompletion = vi.fn();
  const mockDownloadPdfAsBase64 = vi.fn();

  // Chainable supabase query builder
  mockEq.mockImplementation(() => ({
    eq: mockEq,
    single: mockSingle,
  }));

  mockSelect.mockImplementation(() => ({
    eq: mockEq,
    single: mockSingle,
  }));

  mockFrom.mockImplementation(() => ({
    select: mockSelect,
  }));

  return {
    mockSingle,
    mockEq,
    mockSelect,
    mockFrom,
    mockRpc,
    mockChatCompletion,
    mockDownloadPdfAsBase64,
  };
});

vi.mock('@/lib/supabase/server', () => ({
  createClient: vi.fn().mockResolvedValue({
    from: mockFrom,
    rpc: mockRpc,
  }),
}));

vi.mock('@/lib/openrouter', () => ({
  chatCompletion: mockChatCompletion,
  downloadPdfAsBase64: mockDownloadPdfAsBase64,
}));

import { generateSummaryForPaper } from './summary-generation.service';

// ============================================================================
// TESTS
// ============================================================================

describe('summary-generation.service', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Reset chainable returns after clearAllMocks
    mockEq.mockImplementation(() => ({
      eq: mockEq,
      single: mockSingle,
    }));

    mockSelect.mockImplementation(() => ({
      eq: mockEq,
      single: mockSingle,
    }));

    mockFrom.mockImplementation(() => ({
      select: mockSelect,
    }));
  });

  // --------------------------------------------------------------------------
  // generateSummaryForPaper - URL success
  // --------------------------------------------------------------------------
  it('returns generated summary and saves via RPC when URL-based PDF call succeeds', async () => {
    mockSingle.mockResolvedValueOnce({
      data: {
        summaries: null,
        status: 'partially_completed',
        pdf_url: 'https://arxiv.org/pdf/2301.12345',
        arxiv_id: '2301.12345',
      },
      error: null,
    });

    mockChatCompletion.mockResolvedValueOnce({
      text: 'Generated summary',
      promptTokens: 100,
      completionTokens: 200,
      cost: 0.01,
    });

    mockRpc.mockResolvedValueOnce({
      data: [{ was_set: true }],
      error: null,
    });

    const result = await generateSummaryForPaper('test-uuid');

    expect(result.summary).toBe('Generated summary');
    expect(result.alreadyExisted).toBe(false);
    expect(mockChatCompletion).toHaveBeenCalledTimes(1);
    expect(mockRpc).toHaveBeenCalledWith('set_paper_summary_if_null', {
      p_paper_uuid: 'test-uuid',
      p_summary: 'Generated summary',
    });
  });

  // --------------------------------------------------------------------------
  // generateSummaryForPaper - Base64 fallback
  // --------------------------------------------------------------------------
  it('falls back to base64 PDF when URL-based call fails', async () => {
    mockSingle.mockResolvedValueOnce({
      data: {
        summaries: null,
        status: 'partially_completed',
        pdf_url: 'https://arxiv.org/pdf/2301.12345',
        arxiv_id: '2301.12345',
      },
      error: null,
    });

    // First call fails (URL-based), second call succeeds (base64)
    mockChatCompletion
      .mockRejectedValueOnce(new Error('Provider returned error'))
      .mockResolvedValueOnce({
        text: 'Generated summary',
        promptTokens: 100,
        completionTokens: 200,
        cost: 0.01,
      });

    mockDownloadPdfAsBase64.mockResolvedValueOnce('data:application/pdf;base64,fakebase64');

    mockRpc.mockResolvedValueOnce({
      data: [{ was_set: true }],
      error: null,
    });

    const result = await generateSummaryForPaper('test-uuid');

    expect(result.summary).toBe('Generated summary');
    expect(mockChatCompletion).toHaveBeenCalledTimes(2);
    expect(mockDownloadPdfAsBase64).toHaveBeenCalledWith('https://arxiv.org/pdf/2301.12345');

    // Verify the second chatCompletion call uses base64 file_data
    const secondCallMessages = mockChatCompletion.mock.calls[1][0];
    const userMessage = secondCallMessages[1];
    const filePart = userMessage.content[1];
    expect(filePart.file.file_data).toMatch(/^data:application\/pdf;base64,/);
  });

  // --------------------------------------------------------------------------
  // generateSummaryForPaper - Both fail
  // --------------------------------------------------------------------------
  it('throws when both URL and base64 fallback fail', async () => {
    mockSingle.mockResolvedValueOnce({
      data: {
        summaries: null,
        status: 'partially_completed',
        pdf_url: 'https://arxiv.org/pdf/2301.12345',
        arxiv_id: '2301.12345',
      },
      error: null,
    });

    mockChatCompletion
      .mockRejectedValueOnce(new Error('Provider returned error'))
      .mockRejectedValueOnce(new Error('Provider returned error again'));

    mockDownloadPdfAsBase64.mockResolvedValueOnce('data:application/pdf;base64,fakebase64');

    await expect(generateSummaryForPaper('test-uuid')).rejects.toThrow(
      'Provider returned error again'
    );

    expect(mockChatCompletion).toHaveBeenCalledTimes(2);
  });

  // --------------------------------------------------------------------------
  // generateSummaryForPaper - Already exists
  // --------------------------------------------------------------------------
  it('returns existing summary without calling LLM when summary already exists', async () => {
    mockSingle.mockResolvedValueOnce({
      data: {
        summaries: { five_minute_summary: 'Existing summary text' },
        status: 'completed',
        pdf_url: 'https://arxiv.org/pdf/2301.12345',
        arxiv_id: '2301.12345',
      },
      error: null,
    });

    const result = await generateSummaryForPaper('test-uuid');

    expect(result.summary).toBe('Existing summary text');
    expect(result.alreadyExisted).toBe(true);
    expect(mockChatCompletion).not.toHaveBeenCalled();
    expect(mockRpc).not.toHaveBeenCalled();
  });
});
