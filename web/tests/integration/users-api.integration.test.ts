/**
 * Users API Integration Tests (Supabase Auth)
 *
 * Tests for user API endpoints with Supabase authentication mocking.
 * - GET /api/users/me/list - user's paper list
 * - GET/POST/DELETE /api/users/me/list/[uuid] - manage list items
 * - GET /api/users/me/requests - user's paper requests
 * - GET/POST/DELETE /api/users/me/requests/[arxivId] - manage requests
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { testApiHandler } from 'next-test-api-route-handler';

// ============================================================================
// MOCKS
// ============================================================================

/**
 * Mock Supabase client for testing authentication
 */
const mockSupabaseClient = {
  auth: {
    getUser: vi.fn(),
  },
};

/**
 * Mock createClient function from Supabase server module
 */
vi.mock('@/lib/supabase/server', () => ({
  createClient: vi.fn(() => Promise.resolve(mockSupabaseClient)),
}));

/**
 * Mock Prisma client for database operations
 */
const prismaMock = {
  paper: {
    findUnique: vi.fn(),
    findMany: vi.fn(),
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
    deleteMany: vi.fn(),
  },
  user: {
    findUnique: vi.fn(),
  },
};

vi.mock('@/lib/db', () => ({
  prisma: prismaMock,
}));

// ============================================================================
// TEST UTILITIES
// ============================================================================

const TEST_USER_ID = 'test-supabase-user-id';
const TEST_USER_EMAIL = 'test@example.com';

/**
 * Generates a random UUID for testing.
 * @returns A random UUID string
 */
function generateTestUuid(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Generates a test arXiv ID.
 * @returns A valid arXiv ID format string
 */
function generateTestArxivId(): string {
  const year = Math.floor(Math.random() * 10) + 20;
  const month = String(Math.floor(Math.random() * 12) + 1).padStart(2, '0');
  const number = String(Math.floor(Math.random() * 99999)).padStart(5, '0');
  return `${year}${month}.${number}`;
}

/**
 * Resets all mocks before each test.
 */
function resetAllMocks(): void {
  vi.clearAllMocks();

  // Reset Supabase auth to return unauthenticated by default
  mockSupabaseClient.auth.getUser.mockResolvedValue({
    data: { user: null },
    error: new Error('Not authenticated'),
  });
}

/**
 * Sets up Supabase auth mock to return an authenticated user.
 * @param userId - User ID to return
 * @param email - User email to return
 */
function mockSupabaseAuthenticated(
  userId: string = TEST_USER_ID,
  email: string = TEST_USER_EMAIL
): void {
  mockSupabaseClient.auth.getUser.mockResolvedValue({
    data: {
      user: {
        id: userId,
        email: email,
      },
    },
    error: null,
  });
}

// ============================================================================
// TESTS - USER LIST
// ============================================================================

describe('Users API - GET /api/users/me/list', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  it('returns 401 when not authenticated', async () => {
    const appHandler = await import('@/app/api/users/me/list/route');

    await testApiHandler({
      appHandler,
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'GET' });

        expect(response.status).toBe(401);

        const data = await response.json();
        expect(data).toHaveProperty('error');
        expect(data.error.toLowerCase()).toContain('unauthorized');
      },
    });
  });

  it('returns user list when authenticated', async () => {
    mockSupabaseAuthenticated();

    // Mock userList.findMany to return a list with papers
    prismaMock.userList.findMany.mockResolvedValue([
      {
        createdAt: new Date(),
        paper: {
          paperUuid: generateTestUuid(),
          title: 'Test Paper',
          authors: 'Test Author',
          thumbnailDataUrl: null,
          slugs: [{ slug: 'test-slug' }],
        },
      },
    ]);

    const appHandler = await import('@/app/api/users/me/list/route');

    await testApiHandler({
      appHandler,
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'GET' });

        expect(response.status).toBe(200);

        const data = await response.json();
        expect(Array.isArray(data)).toBe(true);
        expect(data).toHaveLength(1);
        expect(data[0]).toHaveProperty('paperUuid');
        expect(data[0]).toHaveProperty('title', 'Test Paper');
      },
    });
  });

  it('returns empty array when user has no papers in list', async () => {
    mockSupabaseAuthenticated();
    prismaMock.userList.findMany.mockResolvedValue([]);

    const appHandler = await import('@/app/api/users/me/list/route');

    await testApiHandler({
      appHandler,
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'GET' });

        expect(response.status).toBe(200);

        const data = await response.json();
        expect(Array.isArray(data)).toBe(true);
        expect(data).toHaveLength(0);
      },
    });
  });
});

// ============================================================================
// TESTS - USER LIST ITEM (GET)
// ============================================================================

describe('Users API - GET /api/users/me/list/[uuid]', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  it('returns 401 when not authenticated', async () => {
    const appHandler = await import('@/app/api/users/me/list/[uuid]/route');
    const uuid = generateTestUuid();

    await testApiHandler({
      appHandler,
      params: { uuid },
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'GET' });

        expect(response.status).toBe(401);

        const data = await response.json();
        expect(data).toHaveProperty('error');
        expect(data.error.toLowerCase()).toContain('unauthorized');
      },
    });
  });

  it('returns exists: true when paper is in user list', async () => {
    mockSupabaseAuthenticated();

    // Mock paper lookup
    prismaMock.paper.findUnique.mockResolvedValue({ id: 1 });
    // Mock userList lookup - paper exists in list
    prismaMock.userList.findUnique.mockResolvedValue({
      userId: TEST_USER_ID,
      paperId: 1,
    });

    const appHandler = await import('@/app/api/users/me/list/[uuid]/route');
    const uuid = generateTestUuid();

    await testApiHandler({
      appHandler,
      params: { uuid },
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'GET' });

        expect(response.status).toBe(200);

        const data = await response.json();
        expect(data).toHaveProperty('exists', true);
      },
    });
  });

  it('returns exists: false when paper is not in user list', async () => {
    mockSupabaseAuthenticated();

    // Mock paper lookup
    prismaMock.paper.findUnique.mockResolvedValue({ id: 1 });
    // Mock userList lookup - paper not in list
    prismaMock.userList.findUnique.mockResolvedValue(null);

    const appHandler = await import('@/app/api/users/me/list/[uuid]/route');
    const uuid = generateTestUuid();

    await testApiHandler({
      appHandler,
      params: { uuid },
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'GET' });

        expect(response.status).toBe(200);

        const data = await response.json();
        expect(data).toHaveProperty('exists', false);
      },
    });
  });

  it('returns exists: false when paper does not exist', async () => {
    mockSupabaseAuthenticated();

    // Mock paper not found
    prismaMock.paper.findUnique.mockResolvedValue(null);

    const appHandler = await import('@/app/api/users/me/list/[uuid]/route');
    const uuid = generateTestUuid();

    await testApiHandler({
      appHandler,
      params: { uuid },
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'GET' });

        expect(response.status).toBe(200);

        const data = await response.json();
        expect(data).toHaveProperty('exists', false);
      },
    });
  });
});

// ============================================================================
// TESTS - USER LIST ITEM (POST)
// ============================================================================

describe('Users API - POST /api/users/me/list/[uuid]', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  it('returns 401 when not authenticated', async () => {
    const appHandler = await import('@/app/api/users/me/list/[uuid]/route');
    const uuid = generateTestUuid();

    await testApiHandler({
      appHandler,
      params: { uuid },
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'POST' });

        expect(response.status).toBe(401);

        const data = await response.json();
        expect(data).toHaveProperty('error');
        expect(data.error.toLowerCase()).toContain('unauthorized');
      },
    });
  });

  it('adds paper to list when authenticated', async () => {
    mockSupabaseAuthenticated();

    // Mock user exists
    prismaMock.user.findUnique.mockResolvedValue({ id: TEST_USER_ID });
    // Mock paper exists
    prismaMock.paper.findUnique.mockResolvedValue({ id: 1, paperUuid: generateTestUuid() });
    // Mock paper not already in list
    prismaMock.userList.findUnique.mockResolvedValue(null);
    // Mock successful creation
    prismaMock.userList.create.mockResolvedValue({
      userId: TEST_USER_ID,
      paperId: 1,
    });

    const appHandler = await import('@/app/api/users/me/list/[uuid]/route');
    const uuid = generateTestUuid();

    await testApiHandler({
      appHandler,
      params: { uuid },
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'POST' });

        expect(response.status).toBe(200);

        const data = await response.json();
        expect(data).toHaveProperty('created', true);
      },
    });
  });

  it('returns created: false when paper already in list', async () => {
    mockSupabaseAuthenticated();

    // Mock user exists
    prismaMock.user.findUnique.mockResolvedValue({ id: TEST_USER_ID });
    // Mock paper exists
    prismaMock.paper.findUnique.mockResolvedValue({ id: 1, paperUuid: generateTestUuid() });
    // Mock paper already in list
    prismaMock.userList.findUnique.mockResolvedValue({
      userId: TEST_USER_ID,
      paperId: 1,
    });

    const appHandler = await import('@/app/api/users/me/list/[uuid]/route');
    const uuid = generateTestUuid();

    await testApiHandler({
      appHandler,
      params: { uuid },
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'POST' });

        expect(response.status).toBe(200);

        const data = await response.json();
        expect(data).toHaveProperty('created', false);
      },
    });
  });

  it('returns 404 when paper does not exist', async () => {
    mockSupabaseAuthenticated();

    // Mock user exists
    prismaMock.user.findUnique.mockResolvedValue({ id: TEST_USER_ID });
    // Mock paper not found
    prismaMock.paper.findUnique.mockResolvedValue(null);

    const appHandler = await import('@/app/api/users/me/list/[uuid]/route');
    const uuid = generateTestUuid();

    await testApiHandler({
      appHandler,
      params: { uuid },
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'POST' });

        expect(response.status).toBe(404);

        const data = await response.json();
        expect(data).toHaveProperty('error');
        expect(data.error.toLowerCase()).toContain('paper not found');
      },
    });
  });
});

// ============================================================================
// TESTS - USER LIST ITEM (DELETE)
// ============================================================================

describe('Users API - DELETE /api/users/me/list/[uuid]', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  it('returns 401 when not authenticated', async () => {
    const appHandler = await import('@/app/api/users/me/list/[uuid]/route');
    const uuid = generateTestUuid();

    await testApiHandler({
      appHandler,
      params: { uuid },
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'DELETE' });

        expect(response.status).toBe(401);

        const data = await response.json();
        expect(data).toHaveProperty('error');
        expect(data.error.toLowerCase()).toContain('unauthorized');
      },
    });
  });

  it('removes paper from list when authenticated', async () => {
    mockSupabaseAuthenticated();

    // Mock paper exists
    prismaMock.paper.findUnique.mockResolvedValue({ id: 1 });
    // Mock successful deletion
    prismaMock.userList.deleteMany.mockResolvedValue({ count: 1 });

    const appHandler = await import('@/app/api/users/me/list/[uuid]/route');
    const uuid = generateTestUuid();

    await testApiHandler({
      appHandler,
      params: { uuid },
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'DELETE' });

        expect(response.status).toBe(200);

        const data = await response.json();
        expect(data).toHaveProperty('deleted', true);
      },
    });
  });

  it('returns deleted: false when paper not in list', async () => {
    mockSupabaseAuthenticated();

    // Mock paper exists
    prismaMock.paper.findUnique.mockResolvedValue({ id: 1 });
    // Mock no deletion (paper wasn't in list)
    prismaMock.userList.deleteMany.mockResolvedValue({ count: 0 });

    const appHandler = await import('@/app/api/users/me/list/[uuid]/route');
    const uuid = generateTestUuid();

    await testApiHandler({
      appHandler,
      params: { uuid },
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'DELETE' });

        expect(response.status).toBe(200);

        const data = await response.json();
        expect(data).toHaveProperty('deleted', false);
      },
    });
  });
});

// ============================================================================
// TESTS - USER REQUESTS
// ============================================================================

describe('Users API - GET /api/users/me/requests', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  it('returns 401 when not authenticated', async () => {
    const appHandler = await import('@/app/api/users/me/requests/route');

    await testApiHandler({
      appHandler,
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'GET' });

        expect(response.status).toBe(401);

        const data = await response.json();
        expect(data).toHaveProperty('error');
        expect(data.error.toLowerCase()).toContain('unauthorized');
      },
    });
  });

  it('returns user requests when authenticated', async () => {
    mockSupabaseAuthenticated();

    const testArxivId = generateTestArxivId();
    prismaMock.userRequest.findMany.mockResolvedValue([
      {
        arxivId: testArxivId,
        title: 'Test Paper',
        authors: 'Test Author',
        createdAt: new Date(),
        isProcessed: false,
        processedSlug: null,
      },
    ]);

    const appHandler = await import('@/app/api/users/me/requests/route');

    await testApiHandler({
      appHandler,
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'GET' });

        expect(response.status).toBe(200);

        const data = await response.json();
        expect(Array.isArray(data)).toBe(true);
        expect(data).toHaveLength(1);
        expect(data[0]).toHaveProperty('arxivId', testArxivId);
      },
    });
  });

  it('returns empty array when user has no requests', async () => {
    mockSupabaseAuthenticated();
    prismaMock.userRequest.findMany.mockResolvedValue([]);

    const appHandler = await import('@/app/api/users/me/requests/route');

    await testApiHandler({
      appHandler,
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'GET' });

        expect(response.status).toBe(200);

        const data = await response.json();
        expect(Array.isArray(data)).toBe(true);
        expect(data).toHaveLength(0);
      },
    });
  });
});

// ============================================================================
// TESTS - USER REQUEST ITEM (GET)
// ============================================================================

describe('Users API - GET /api/users/me/requests/[arxivId]', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  it('returns 401 when not authenticated', async () => {
    const appHandler = await import('@/app/api/users/me/requests/[arxivId]/route');
    const arxivId = generateTestArxivId();

    await testApiHandler({
      appHandler,
      params: { arxivId },
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'GET' });

        expect(response.status).toBe(401);

        const data = await response.json();
        expect(data).toHaveProperty('error');
        expect(data.error.toLowerCase()).toContain('unauthorized');
      },
    });
  });

  it('returns exists: true when request exists', async () => {
    mockSupabaseAuthenticated();

    const arxivId = generateTestArxivId();
    prismaMock.userRequest.findUnique.mockResolvedValue({
      userId: TEST_USER_ID,
      arxivId: arxivId,
    });

    const appHandler = await import('@/app/api/users/me/requests/[arxivId]/route');

    await testApiHandler({
      appHandler,
      params: { arxivId },
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'GET' });

        expect(response.status).toBe(200);

        const data = await response.json();
        expect(data).toHaveProperty('exists', true);
      },
    });
  });

  it('returns exists: false when request does not exist', async () => {
    mockSupabaseAuthenticated();
    prismaMock.userRequest.findUnique.mockResolvedValue(null);

    const appHandler = await import('@/app/api/users/me/requests/[arxivId]/route');
    const arxivId = generateTestArxivId();

    await testApiHandler({
      appHandler,
      params: { arxivId },
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'GET' });

        expect(response.status).toBe(200);

        const data = await response.json();
        expect(data).toHaveProperty('exists', false);
      },
    });
  });
});

// ============================================================================
// TESTS - USER REQUEST ITEM (POST)
// ============================================================================

describe('Users API - POST /api/users/me/requests/[arxivId]', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  it('returns 401 when not authenticated', async () => {
    const appHandler = await import('@/app/api/users/me/requests/[arxivId]/route');
    const arxivId = generateTestArxivId();

    await testApiHandler({
      appHandler,
      params: { arxivId },
      test: async ({ fetch }) => {
        const response = await fetch({
          method: 'POST',
          body: JSON.stringify({ title: 'Test Paper', authors: 'Test Author' }),
          headers: { 'Content-Type': 'application/json' },
        });

        expect(response.status).toBe(401);

        const data = await response.json();
        expect(data).toHaveProperty('error');
        expect(data.error.toLowerCase()).toContain('unauthorized');
      },
    });
  });

  it('adds request when authenticated', async () => {
    mockSupabaseAuthenticated();

    // Mock user exists
    prismaMock.user.findUnique.mockResolvedValue({ id: TEST_USER_ID });
    // Mock request does not exist yet
    prismaMock.userRequest.findUnique.mockResolvedValue(null);
    // Mock successful creation
    prismaMock.userRequest.create.mockResolvedValue({
      userId: TEST_USER_ID,
      arxivId: generateTestArxivId(),
      title: 'Test Paper',
      authors: 'Test Author',
    });

    const appHandler = await import('@/app/api/users/me/requests/[arxivId]/route');
    const arxivId = generateTestArxivId();

    await testApiHandler({
      appHandler,
      params: { arxivId },
      test: async ({ fetch }) => {
        const response = await fetch({
          method: 'POST',
          body: JSON.stringify({ title: 'Test Paper', authors: 'Test Author' }),
          headers: { 'Content-Type': 'application/json' },
        });

        expect(response.status).toBe(200);

        const data = await response.json();
        expect(data).toHaveProperty('created', true);
      },
    });
  });

  it('returns created: false when request already exists', async () => {
    mockSupabaseAuthenticated();

    const arxivId = generateTestArxivId();
    // Mock user exists
    prismaMock.user.findUnique.mockResolvedValue({ id: TEST_USER_ID });
    // Mock request already exists
    prismaMock.userRequest.findUnique.mockResolvedValue({
      userId: TEST_USER_ID,
      arxivId: arxivId,
    });

    const appHandler = await import('@/app/api/users/me/requests/[arxivId]/route');

    await testApiHandler({
      appHandler,
      params: { arxivId },
      test: async ({ fetch }) => {
        const response = await fetch({
          method: 'POST',
          body: JSON.stringify({ title: 'Test Paper', authors: 'Test Author' }),
          headers: { 'Content-Type': 'application/json' },
        });

        expect(response.status).toBe(200);

        const data = await response.json();
        expect(data).toHaveProperty('created', false);
      },
    });
  });

  it('handles request without title and authors', async () => {
    mockSupabaseAuthenticated();

    // Mock user exists
    prismaMock.user.findUnique.mockResolvedValue({ id: TEST_USER_ID });
    // Mock request does not exist yet
    prismaMock.userRequest.findUnique.mockResolvedValue(null);
    // Mock successful creation
    prismaMock.userRequest.create.mockResolvedValue({
      userId: TEST_USER_ID,
      arxivId: generateTestArxivId(),
      title: null,
      authors: null,
    });

    const appHandler = await import('@/app/api/users/me/requests/[arxivId]/route');
    const arxivId = generateTestArxivId();

    await testApiHandler({
      appHandler,
      params: { arxivId },
      test: async ({ fetch }) => {
        const response = await fetch({
          method: 'POST',
          body: JSON.stringify({}),
          headers: { 'Content-Type': 'application/json' },
        });

        expect(response.status).toBe(200);

        const data = await response.json();
        expect(data).toHaveProperty('created', true);
      },
    });
  });
});

// ============================================================================
// TESTS - USER REQUEST ITEM (DELETE)
// ============================================================================

describe('Users API - DELETE /api/users/me/requests/[arxivId]', () => {
  beforeEach(() => {
    resetAllMocks();
  });

  it('returns 401 when not authenticated', async () => {
    const appHandler = await import('@/app/api/users/me/requests/[arxivId]/route');
    const arxivId = generateTestArxivId();

    await testApiHandler({
      appHandler,
      params: { arxivId },
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'DELETE' });

        expect(response.status).toBe(401);

        const data = await response.json();
        expect(data).toHaveProperty('error');
        expect(data.error.toLowerCase()).toContain('unauthorized');
      },
    });
  });

  it('removes request when authenticated', async () => {
    mockSupabaseAuthenticated();
    prismaMock.userRequest.deleteMany.mockResolvedValue({ count: 1 });

    const appHandler = await import('@/app/api/users/me/requests/[arxivId]/route');
    const arxivId = generateTestArxivId();

    await testApiHandler({
      appHandler,
      params: { arxivId },
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'DELETE' });

        expect(response.status).toBe(200);

        const data = await response.json();
        expect(data).toHaveProperty('deleted', true);
      },
    });
  });

  it('returns deleted: false when request does not exist', async () => {
    mockSupabaseAuthenticated();
    prismaMock.userRequest.deleteMany.mockResolvedValue({ count: 0 });

    const appHandler = await import('@/app/api/users/me/requests/[arxivId]/route');
    const arxivId = generateTestArxivId();

    await testApiHandler({
      appHandler,
      params: { arxivId },
      test: async ({ fetch }) => {
        const response = await fetch({ method: 'DELETE' });

        expect(response.status).toBe(200);

        const data = await response.json();
        expect(data).toHaveProperty('deleted', false);
      },
    });
  });
});
