/**
 * Integration Test Setup
 *
 * Provides common mocks and helpers for API route integration tests.
 * - Mocks Prisma client for database operations
 * - Mocks Supabase client for user authentication
 * - Mocks admin auth helper for admin endpoints
 * - Provides test data factories
 */

import { vi } from 'vitest';
import { NextResponse } from 'next/server';

// ============================================================================
// PRISMA MOCK
// ============================================================================

/**
 * Mocked Prisma client with all methods as vi.fn()
 */
export const prismaMock = {
  paper: {
    findUnique: vi.fn(),
    findMany: vi.fn(),
    findFirst: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    count: vi.fn(),
    upsert: vi.fn(),
  },
  paperSlug: {
    findUnique: vi.fn(),
    findFirst: vi.fn(),
    create: vi.fn(),
    deleteMany: vi.fn(),
  },
  paperStatusHistory: {
    findFirst: vi.fn(),
    findUnique: vi.fn(),
  },
  userList: {
    findUnique: vi.fn(),
    findMany: vi.fn(),
    findFirst: vi.fn(),
    create: vi.fn(),
    delete: vi.fn(),
    deleteMany: vi.fn(),
  },
  userRequest: {
    findUnique: vi.fn(),
    findMany: vi.fn(),
    findFirst: vi.fn(),
    create: vi.fn(),
    delete: vi.fn(),
    deleteMany: vi.fn(),
  },
  user: {
    findUnique: vi.fn(),
    findFirst: vi.fn(),
    create: vi.fn(),
    upsert: vi.fn(),
  },
  $queryRaw: vi.fn(),
  $executeRaw: vi.fn(),
};

vi.mock('@/lib/db', () => ({
  prisma: prismaMock,
}));

// ============================================================================
// SUPABASE AUTH MOCK
// ============================================================================

/**
 * Mock session for authenticated user tests
 */
export interface MockSession {
  user: {
    id: string;
    email: string;
  };
}

/**
 * Default mock session for testing
 */
export const defaultMockSession: MockSession = {
  user: {
    id: 'test-user-id',
    email: 'test@example.com',
  },
};

/**
 * Mocked Supabase client with auth.getUser method
 */
export const mockSupabaseClient = {
  auth: {
    getUser: vi.fn(),
  },
};

vi.mock('@/lib/supabase/server', () => ({
  createClient: vi.fn(() => Promise.resolve(mockSupabaseClient)),
}));

// ============================================================================
// ADMIN AUTH MOCK
// ============================================================================

/**
 * Mocked adminGuard function.
 * Returns null to allow access, or a NextResponse to deny access.
 */
export const adminGuardMock = vi.fn();

vi.mock('@/lib/admin-auth', () => ({
  adminGuard: adminGuardMock,
}));

// ============================================================================
// ENV MOCK
// ============================================================================

vi.mock('@/lib/env', () => ({
  env: {
    ADMIN_BASIC_PASSWORD: 'testpassword',
    DATABASE_URL: 'mock://database',
  },
}));

// ============================================================================
// TEST UTILITIES
// ============================================================================

/**
 * Generates a random UUID for testing.
 * @returns A random UUID string
 */
export function generateTestUuid(): string {
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
export function generateTestArxivId(): string {
  const year = Math.floor(Math.random() * 10) + 20; // 20-29
  const month = String(Math.floor(Math.random() * 12) + 1).padStart(2, '0');
  const number = String(Math.floor(Math.random() * 99999)).padStart(5, '0');
  return `${year}${month}.${number}`;
}

/**
 * Creates a test paper import payload.
 * @param uuid - Optional UUID to use
 * @returns Paper JSON object for import
 */
export function createTestPaperPayload(uuid?: string): Record<string, unknown> {
  const paperUuid = uuid || generateTestUuid();
  return {
    paper_uuid: paperUuid,
    arxiv_id: generateTestArxivId(),
    title: 'Test Paper Title',
    authors: ['Test Author 1', 'Test Author 2'],
    abstract: 'This is a test abstract for the paper.',
    source_url: 'https://arxiv.org/abs/2301.00001',
    summary: {
      overview: 'Test overview',
      key_points: ['Point 1', 'Point 2'],
    },
  };
}

/**
 * Creates a mock paper object for database responses.
 * @param overrides - Properties to override
 * @returns Mock paper object
 */
export function createMockPaper(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    paperUuid: generateTestUuid(),
    arxivId: generateTestArxivId(),
    title: 'Test Paper Title',
    authors: 'Test Author 1, Test Author 2',
    abstract: 'This is a test abstract.',
    sourceUrl: 'https://arxiv.org/abs/2301.00001',
    status: 'completed',
    createdAt: new Date(),
    updatedAt: new Date(),
    ...overrides,
  };
}

/**
 * Creates HTTP Basic auth header for admin endpoints.
 * @returns Authorization header value
 */
export function getAdminAuthHeader(): string {
  const credentials = Buffer.from('admin:testpassword').toString('base64');
  return `Basic ${credentials}`;
}

/**
 * Creates invalid HTTP Basic auth header for testing auth failures.
 * @returns Authorization header with wrong credentials
 */
export function getInvalidAdminAuthHeader(): string {
  const credentials = Buffer.from('admin:wrongpassword').toString('base64');
  return `Basic ${credentials}`;
}

/**
 * Resets all mocks before each test.
 * Call this in beforeEach.
 */
export function resetAllMocks(): void {
  vi.clearAllMocks();

  // Reset Supabase auth mock to return unauthenticated by default
  mockSupabaseClient.auth.getUser.mockResolvedValue({
    data: { user: null },
    error: new Error('Not authenticated'),
  });

  // Reset admin auth mock to return 401 by default (unauthorized)
  adminGuardMock.mockReturnValue(
    NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  );
}

/**
 * Sets up Supabase auth mock to return an authenticated user.
 * @param session - Session object to return (uses default if not provided)
 */
export function mockAuthenticatedSession(session: MockSession = defaultMockSession): void {
  mockSupabaseClient.auth.getUser.mockResolvedValue({
    data: {
      user: {
        id: session.user.id,
        email: session.user.email,
      },
    },
    error: null,
  });
}

/**
 * Sets up admin auth mock to allow access.
 * Returns null to indicate no error (admin is authenticated).
 */
export function mockAdminAuthenticated(): void {
  adminGuardMock.mockReturnValue(null);
}
