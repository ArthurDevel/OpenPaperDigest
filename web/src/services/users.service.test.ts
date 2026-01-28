/**
 * Unit tests for the User Service
 *
 * Tests the business logic for:
 * - User sync from auth provider
 * - User list management (add, remove, check papers)
 * - User request management (paper processing requests)
 * - Aggregated request retrieval for admin
 * - Processing metrics retrieval
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the db module
vi.mock('@/lib/db', () => ({
  prisma: {
    user: {
      findUnique: vi.fn(),
      create: vi.fn(),
    },
    paper: {
      findUnique: vi.fn(),
      create: vi.fn(),
    },
    userList: {
      findUnique: vi.fn(),
      findMany: vi.fn(),
      create: vi.fn(),
      deleteMany: vi.fn(),
    },
    userRequest: {
      findUnique: vi.fn(),
      findMany: vi.fn(),
      create: vi.fn(),
      delete: vi.fn(),
      deleteMany: vi.fn(),
    },
  },
}));

import { prisma } from '@/lib/db';
import {
  syncNewUser,
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

const mockUser = vi.mocked(prisma.user);
const mockPaper = vi.mocked(prisma.paper);
const mockUserList = vi.mocked(prisma.userList);
const mockUserRequest = vi.mocked(prisma.userRequest);

beforeEach(() => {
  vi.clearAllMocks();
});

// ============================================================================
// syncNewUser TESTS
// ============================================================================

describe('syncNewUser', () => {
  it('returns { created: false } when user already exists', async () => {
    mockUser.findUnique.mockResolvedValue({
      id: 'user-123',
      email: 'test@example.com',
      createdAt: new Date(),
    });

    const result = await syncNewUser({ id: 'user-123', email: 'test@example.com' });

    expect(result).toEqual({ created: false });
    expect(mockUser.findUnique).toHaveBeenCalledWith({ where: { id: 'user-123' } });
    expect(mockUser.create).not.toHaveBeenCalled();
  });

  it('creates user and returns { created: true } when user does not exist', async () => {
    mockUser.findUnique.mockResolvedValue(null);
    mockUser.create.mockResolvedValue({
      id: 'user-123',
      email: 'test@example.com',
      createdAt: new Date(),
    });

    const result = await syncNewUser({ id: 'user-123', email: 'test@example.com' });

    expect(result).toEqual({ created: true });
    expect(mockUser.create).toHaveBeenCalledWith({
      data: { id: 'user-123', email: 'test@example.com' },
    });
  });
});

// ============================================================================
// addToList TESTS
// ============================================================================

describe('addToList', () => {
  it('throws "User not found: {id}" when user does not exist', async () => {
    mockUser.findUnique.mockResolvedValue(null);

    await expect(addToList('user-123', 'paper-uuid')).rejects.toThrow(
      'User not found: user-123'
    );
  });

  it('throws "Paper not found: {uuid}" when paper does not exist', async () => {
    mockUser.findUnique.mockResolvedValue({
      id: 'user-123',
      email: 'test@example.com',
      createdAt: new Date(),
    });
    mockPaper.findUnique.mockResolvedValue(null);

    await expect(addToList('user-123', 'paper-uuid')).rejects.toThrow(
      'Paper not found: paper-uuid'
    );
  });

  it('returns { created: false } when paper is already in list', async () => {
    mockUser.findUnique.mockResolvedValue({
      id: 'user-123',
      email: 'test@example.com',
      createdAt: new Date(),
    });
    mockPaper.findUnique.mockResolvedValue({ id: 1 });
    mockUserList.findUnique.mockResolvedValue({
      id: BigInt(1),
      userId: 'user-123',
      paperId: 1,
      createdAt: new Date(),
    });

    const result = await addToList('user-123', 'paper-uuid');

    expect(result).toEqual({ created: false });
    expect(mockUserList.create).not.toHaveBeenCalled();
  });

  it('creates entry and returns { created: true } when paper is not in list', async () => {
    mockUser.findUnique.mockResolvedValue({
      id: 'user-123',
      email: 'test@example.com',
      createdAt: new Date(),
    });
    mockPaper.findUnique.mockResolvedValue({ id: 1 });
    mockUserList.findUnique.mockResolvedValue(null);
    mockUserList.create.mockResolvedValue({
      id: BigInt(1),
      userId: 'user-123',
      paperId: 1,
      createdAt: new Date(),
    });

    const result = await addToList('user-123', 'paper-uuid');

    expect(result).toEqual({ created: true });
    expect(mockUserList.create).toHaveBeenCalledWith({
      data: { userId: 'user-123', paperId: 1 },
    });
  });
});

// ============================================================================
// removeFromList TESTS
// ============================================================================

describe('removeFromList', () => {
  it('returns { deleted: false } when paper is not found', async () => {
    mockPaper.findUnique.mockResolvedValue(null);

    const result = await removeFromList('user-123', 'paper-uuid');

    expect(result).toEqual({ deleted: false });
    expect(mockUserList.deleteMany).not.toHaveBeenCalled();
  });

  it('returns { deleted: true } when entry is deleted', async () => {
    mockPaper.findUnique.mockResolvedValue({ id: 1 });
    mockUserList.deleteMany.mockResolvedValue({ count: 1 });

    const result = await removeFromList('user-123', 'paper-uuid');

    expect(result).toEqual({ deleted: true });
    expect(mockUserList.deleteMany).toHaveBeenCalledWith({
      where: { userId: 'user-123', paperId: 1 },
    });
  });

  it('returns { deleted: false } when no entry exists to delete', async () => {
    mockPaper.findUnique.mockResolvedValue({ id: 1 });
    mockUserList.deleteMany.mockResolvedValue({ count: 0 });

    const result = await removeFromList('user-123', 'paper-uuid');

    expect(result).toEqual({ deleted: false });
  });
});

// ============================================================================
// isInList TESTS
// ============================================================================

describe('isInList', () => {
  it('returns { exists: false } when paper is not found', async () => {
    mockPaper.findUnique.mockResolvedValue(null);

    const result = await isInList('user-123', 'paper-uuid');

    expect(result).toEqual({ exists: false });
  });

  it('returns { exists: true } when entry exists', async () => {
    mockPaper.findUnique.mockResolvedValue({ id: 1 });
    mockUserList.findUnique.mockResolvedValue({
      id: BigInt(1),
      userId: 'user-123',
      paperId: 1,
      createdAt: new Date(),
    });

    const result = await isInList('user-123', 'paper-uuid');

    expect(result).toEqual({ exists: true });
  });

  it('returns { exists: false } when entry does not exist', async () => {
    mockPaper.findUnique.mockResolvedValue({ id: 1 });
    mockUserList.findUnique.mockResolvedValue(null);

    const result = await isInList('user-123', 'paper-uuid');

    expect(result).toEqual({ exists: false });
  });
});

// ============================================================================
// addRequest TESTS
// ============================================================================

describe('addRequest', () => {
  it('throws "User not found: {id}" when user does not exist', async () => {
    mockUser.findUnique.mockResolvedValue(null);

    await expect(addRequest('user-123', 'arxiv-123', 'Title', 'Authors')).rejects.toThrow(
      'User not found: user-123'
    );
  });

  it('returns { created: false } when request already exists', async () => {
    mockUser.findUnique.mockResolvedValue({
      id: 'user-123',
      email: 'test@example.com',
      createdAt: new Date(),
    });
    mockUserRequest.findUnique.mockResolvedValue({
      id: BigInt(1),
      userId: 'user-123',
      arxivId: 'arxiv-123',
      title: 'Title',
      authors: 'Authors',
      createdAt: new Date(),
      isProcessed: false,
      processedSlug: null,
    });

    const result = await addRequest('user-123', 'arxiv-123', 'Title', 'Authors');

    expect(result).toEqual({ created: false });
    expect(mockUserRequest.create).not.toHaveBeenCalled();
  });

  it('creates request and returns { created: true } when request does not exist', async () => {
    mockUser.findUnique.mockResolvedValue({
      id: 'user-123',
      email: 'test@example.com',
      createdAt: new Date(),
    });
    mockUserRequest.findUnique.mockResolvedValue(null);
    mockUserRequest.create.mockResolvedValue({
      id: BigInt(1),
      userId: 'user-123',
      arxivId: 'arxiv-123',
      title: 'Title',
      authors: 'Authors',
      createdAt: new Date(),
      isProcessed: false,
      processedSlug: null,
    });

    const result = await addRequest('user-123', 'arxiv-123', 'Title', 'Authors');

    expect(result).toEqual({ created: true });
    expect(mockUserRequest.create).toHaveBeenCalledWith({
      data: {
        userId: 'user-123',
        arxivId: 'arxiv-123',
        title: 'Title',
        authors: 'Authors',
      },
    });
  });

  it('handles null title and authors', async () => {
    mockUser.findUnique.mockResolvedValue({
      id: 'user-123',
      email: 'test@example.com',
      createdAt: new Date(),
    });
    mockUserRequest.findUnique.mockResolvedValue(null);
    mockUserRequest.create.mockResolvedValue({
      id: BigInt(1),
      userId: 'user-123',
      arxivId: 'arxiv-123',
      title: null,
      authors: null,
      createdAt: new Date(),
      isProcessed: false,
      processedSlug: null,
    });

    const result = await addRequest('user-123', 'arxiv-123', null, null);

    expect(result).toEqual({ created: true });
    expect(mockUserRequest.create).toHaveBeenCalledWith({
      data: {
        userId: 'user-123',
        arxivId: 'arxiv-123',
        title: null,
        authors: null,
      },
    });
  });
});

// ============================================================================
// getAggregatedRequests TESTS
// ============================================================================

describe('getAggregatedRequests', () => {
  it('returns empty array when there are no requests', async () => {
    mockUserRequest.findMany.mockResolvedValue([]);

    const result = await getAggregatedRequests();

    expect(result).toEqual([]);
  });

  it('returns single aggregated item with requestCount: 1 for single request', async () => {
    const createdAt = new Date('2024-01-15T10:00:00Z');
    mockUserRequest.findMany.mockResolvedValue([
      {
        id: BigInt(1),
        userId: 'user-123',
        arxivId: '2401.00001',
        title: 'Test Paper',
        authors: 'Test Author',
        createdAt,
        isProcessed: false,
        processedSlug: null,
      },
    ]);

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

    mockUserRequest.findMany.mockResolvedValue([
      {
        id: BigInt(3),
        userId: 'user-789',
        arxivId: '2401.00001',
        title: 'Test Paper',
        authors: 'Test Author',
        createdAt: thirdDate,
        isProcessed: false,
        processedSlug: null,
      },
      {
        id: BigInt(2),
        userId: 'user-456',
        arxivId: '2401.00001',
        title: null,
        authors: null,
        createdAt: secondDate,
        isProcessed: false,
        processedSlug: null,
      },
      {
        id: BigInt(1),
        userId: 'user-123',
        arxivId: '2401.00001',
        title: null,
        authors: null,
        createdAt: firstDate,
        isProcessed: false,
        processedSlug: null,
      },
    ]);

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

    mockUserRequest.findMany.mockResolvedValue([
      // Paper A: 1 request
      {
        id: BigInt(1),
        userId: 'user-1',
        arxivId: 'paper-A',
        title: 'Paper A',
        authors: null,
        createdAt: now,
        isProcessed: false,
        processedSlug: null,
      },
      // Paper B: 2 requests
      {
        id: BigInt(2),
        userId: 'user-1',
        arxivId: 'paper-B',
        title: 'Paper B',
        authors: null,
        createdAt: earlier,
        isProcessed: false,
        processedSlug: null,
      },
      {
        id: BigInt(3),
        userId: 'user-2',
        arxivId: 'paper-B',
        title: null,
        authors: null,
        createdAt: now,
        isProcessed: false,
        processedSlug: null,
      },
      // Paper C: 2 requests but earlier lastRequestedAt
      {
        id: BigInt(4),
        userId: 'user-1',
        arxivId: 'paper-C',
        title: 'Paper C',
        authors: null,
        createdAt: earlier,
        isProcessed: false,
        processedSlug: null,
      },
      {
        id: BigInt(5),
        userId: 'user-2',
        arxivId: 'paper-C',
        title: null,
        authors: null,
        createdAt: earlier,
        isProcessed: false,
        processedSlug: null,
      },
    ]);

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

    mockUserRequest.findMany.mockResolvedValue([
      {
        id: BigInt(1),
        userId: 'user-1',
        arxivId: 'paper-A',
        title: 'Paper A',
        authors: null,
        createdAt: now,
        isProcessed: false,
        processedSlug: null,
      },
      {
        id: BigInt(2),
        userId: 'user-1',
        arxivId: 'paper-B',
        title: 'Paper B',
        authors: null,
        createdAt: now,
        isProcessed: false,
        processedSlug: null,
      },
      {
        id: BigInt(3),
        userId: 'user-1',
        arxivId: 'paper-C',
        title: 'Paper C',
        authors: null,
        createdAt: now,
        isProcessed: false,
        processedSlug: null,
      },
    ]);

    const result = await getAggregatedRequests(2);

    expect(result).toHaveLength(2);
  });

  it('respects offset parameter', async () => {
    const now = new Date();

    mockUserRequest.findMany.mockResolvedValue([
      {
        id: BigInt(1),
        userId: 'user-1',
        arxivId: 'paper-A',
        title: 'Paper A',
        authors: null,
        createdAt: now,
        isProcessed: false,
        processedSlug: null,
      },
      {
        id: BigInt(2),
        userId: 'user-1',
        arxivId: 'paper-B',
        title: 'Paper B',
        authors: null,
        createdAt: now,
        isProcessed: false,
        processedSlug: null,
      },
      {
        id: BigInt(3),
        userId: 'user-1',
        arxivId: 'paper-C',
        title: 'Paper C',
        authors: null,
        createdAt: now,
        isProcessed: false,
        processedSlug: null,
      },
    ]);

    const result = await getAggregatedRequests(10, 1);

    expect(result).toHaveLength(2);
  });

  it('handles processed requests correctly', async () => {
    const now = new Date();

    mockUserRequest.findMany.mockResolvedValue([
      {
        id: BigInt(1),
        userId: 'user-1',
        arxivId: 'paper-A',
        title: 'Paper A',
        authors: 'Author A',
        createdAt: now,
        isProcessed: false,
        processedSlug: null,
      },
      {
        id: BigInt(2),
        userId: 'user-2',
        arxivId: 'paper-A',
        title: null,
        authors: null,
        createdAt: now,
        isProcessed: true,
        processedSlug: 'paper-a-slug',
      },
    ]);

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
    mockPaper.findUnique.mockResolvedValue(null);

    const result = await getProcessingMetrics('user-123', 'paper-uuid');

    expect(result).toBeNull();
  });

  it('returns null when paper was not initiated by user', async () => {
    mockPaper.findUnique.mockResolvedValue({
      paperUuid: 'paper-uuid',
      status: 'completed',
      numPages: 10,
      processingTimeSeconds: 120,
      totalCost: 0.5,
      avgCostPerPage: 0.05,
      startedAt: new Date(),
      finishedAt: new Date(),
      errorMessage: null,
      initiatedByUserId: 'different-user',
    });

    const result = await getProcessingMetrics('user-123', 'paper-uuid');

    expect(result).toBeNull();
  });

  it('returns metrics when paper was initiated by user', async () => {
    const startedAt = new Date('2024-01-15T10:00:00Z');
    const finishedAt = new Date('2024-01-15T10:02:00Z');

    mockPaper.findUnique.mockResolvedValue({
      paperUuid: 'paper-uuid',
      status: 'completed',
      numPages: 10,
      processingTimeSeconds: 120,
      totalCost: 0.5,
      avgCostPerPage: 0.05,
      startedAt,
      finishedAt,
      errorMessage: null,
      initiatedByUserId: 'user-123',
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

    mockPaper.findUnique.mockResolvedValue({
      paperUuid: 'paper-uuid',
      status: 'failed',
      numPages: null,
      processingTimeSeconds: null,
      totalCost: null,
      avgCostPerPage: null,
      startedAt,
      finishedAt: null,
      errorMessage: 'Processing failed due to timeout',
      initiatedByUserId: 'user-123',
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
