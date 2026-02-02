/**
 * Integration Test Setup
 *
 * Provides common mocks and helpers for API route integration tests.
 * - Mocks Supabase client for database operations (chainable query builder)
 * - Mocks Supabase auth for user authentication
 * - Mocks admin auth helper for admin endpoints
 * - Provides test data factories
 */

import { vi } from 'vitest';
import { NextResponse } from 'next/server';

// ============================================================================
// SUPABASE CHAINABLE MOCK
// ============================================================================

/**
 * Mock functions for the Supabase query builder chain.
 * All chainable methods return the chain object.
 * Terminal methods (maybeSingle, single) return promises.
 */
export const mockMaybeSingle = vi.fn();
export const mockSingle = vi.fn();
export const mockLimit = vi.fn();
export const mockRange = vi.fn();
export const mockOrder = vi.fn();
export const mockIn = vi.fn();
export const mockGte = vi.fn();
export const mockLte = vi.fn();
export const mockEq = vi.fn();
export const mockSelect = vi.fn();
export const mockInsert = vi.fn();
export const mockUpdate = vi.fn();
export const mockDelete = vi.fn();
export const mockFrom = vi.fn();

// Default result for awaiting the query builder directly
let defaultQueryResult = { data: null, error: null, count: null };

/**
 * The chainable mock object. This single object is returned by all chainable methods
 * so that chains like `.from().select().eq().order().limit()` work correctly.
 * It's also a thenable so it can be awaited directly.
 */
const chainable = {
  select: mockSelect,
  insert: mockInsert,
  update: mockUpdate,
  delete: mockDelete,
  eq: mockEq,
  in: mockIn,
  gte: mockGte,
  lte: mockLte,
  order: mockOrder,
  limit: mockLimit,
  range: mockRange,
  maybeSingle: mockMaybeSingle,
  single: mockSingle,
  // Make chainable thenable so it can be awaited directly
  then: (resolve: (value: unknown) => unknown) => Promise.resolve(defaultQueryResult).then(resolve),
};

// Configure all chainable methods to return the same chainable object
mockLimit.mockReturnValue(chainable);
mockRange.mockReturnValue(chainable);
mockOrder.mockReturnValue(chainable);
mockIn.mockReturnValue(chainable);
mockGte.mockReturnValue(chainable);
mockLte.mockReturnValue(chainable);
mockEq.mockReturnValue(chainable);
mockSelect.mockReturnValue(chainable);
mockInsert.mockReturnValue(chainable);
mockUpdate.mockReturnValue(chainable);
mockDelete.mockReturnValue(chainable);
mockFrom.mockReturnValue(chainable);

// Default resolved values for terminal methods
mockMaybeSingle.mockResolvedValue({ data: null, error: null });
mockSingle.mockResolvedValue({ data: null, error: null });

/**
 * The mocked Supabase client object.
 */
export const supabaseMock = {
  from: mockFrom,
  auth: {
    getUser: vi.fn(),
  },
};

vi.mock('@/lib/supabase/server', () => ({
  createClient: vi.fn(() => Promise.resolve(supabaseMock)),
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
// SESSION TYPES AND DEFAULTS
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
 * Creates a mock paper object for database responses (snake_case for Supabase).
 * @param overrides - Properties to override
 * @returns Mock paper object
 */
export function createMockPaper(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    paper_uuid: generateTestUuid(),
    arxiv_id: generateTestArxivId(),
    title: 'Test Paper Title',
    authors: 'Test Author 1, Test Author 2',
    abstract: 'This is a test abstract.',
    arxiv_url: 'https://arxiv.org/abs/2301.00001',
    status: 'completed',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
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

  // Reset default query result
  defaultQueryResult = { data: null, error: null, count: null };

  // Reset all chainable methods to return the chainable object
  mockLimit.mockReturnValue(chainable);
  mockRange.mockReturnValue(chainable);
  mockOrder.mockReturnValue(chainable);
  mockIn.mockReturnValue(chainable);
  mockGte.mockReturnValue(chainable);
  mockLte.mockReturnValue(chainable);
  mockEq.mockReturnValue(chainable);
  mockSelect.mockReturnValue(chainable);
  mockInsert.mockReturnValue(chainable);
  mockUpdate.mockReturnValue(chainable);
  mockDelete.mockReturnValue(chainable);
  mockFrom.mockReturnValue(chainable);

  // Reset terminal methods to default values
  mockMaybeSingle.mockResolvedValue({ data: null, error: null });
  mockSingle.mockResolvedValue({ data: null, error: null });

  // Reset Supabase auth mock to return unauthenticated by default
  supabaseMock.auth.getUser.mockResolvedValue({
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
  supabaseMock.auth.getUser.mockResolvedValue({
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

// ============================================================================
// SUPABASE MOCK HELPERS
// ============================================================================

/**
 * Configure mockMaybeSingle to return data for the next call.
 * @param data - Data to return
 */
export function mockQueryReturns(data: unknown): void {
  mockMaybeSingle.mockResolvedValueOnce({ data, error: null });
}

/**
 * Configure mockSingle to return data for the next call.
 * @param data - Data to return
 */
export function mockQueryReturnsSingle(data: unknown): void {
  mockSingle.mockResolvedValueOnce({ data, error: null });
}

/**
 * Configure mockEq to return count result (for count queries).
 * Use this for queries ending with `.select('*', { count: 'exact', head: true }).eq(...)`.
 * @param count - Count to return
 */
export function mockCountReturns(count: number): void {
  // For count queries, the eq() call returns { count, error } directly
  // Also include chainable methods in case more chaining happens
  mockEq.mockReturnValueOnce({
    ...chainable,
    count,
    error: null,
    then: (resolve: (value: unknown) => unknown) => Promise.resolve({ count, error: null }).then(resolve),
  });
}

/**
 * Configure mockGte to return count result (for count queries with gte).
 * Use this for queries ending with `.gte(...)` that return a count.
 * @param count - Count to return
 */
export function mockGteCountReturns(count: number): void {
  mockGte.mockReturnValueOnce({
    ...chainable,
    count,
    error: null,
    then: (resolve: (value: unknown) => unknown) => Promise.resolve({ count, error: null }).then(resolve),
  });
}

/**
 * Configure mockRange to return data (for paginated queries).
 * @param data - Array of data to return
 */
export function mockRangeReturns(data: unknown[]): void {
  mockRange.mockReturnValueOnce({
    ...chainable,
    then: (resolve: (value: unknown) => unknown) => Promise.resolve({ data, error: null }).then(resolve),
  });
}

/**
 * Configure mockLimit to return data (for queries with limit).
 * @param data - Array of data to return
 */
export function mockLimitReturns(data: unknown[]): void {
  mockLimit.mockReturnValueOnce({
    ...chainable,
    then: (resolve: (value: unknown) => unknown) => Promise.resolve({ data, error: null }).then(resolve),
  });
}

/**
 * Configure mockOrder to return data (for ordered queries without range).
 * @param data - Array of data to return
 */
export function mockOrderReturns(data: unknown[]): void {
  mockOrder.mockReturnValueOnce({
    ...chainable,
    then: (resolve: (value: unknown) => unknown) => Promise.resolve({ data, error: null }).then(resolve),
  });
}

/**
 * Configure mockIn to return data (for queries with .in() filter).
 * @param data - Array of data to return
 */
export function mockInReturns(data: unknown[]): void {
  mockIn.mockReturnValueOnce({
    ...chainable,
    then: (resolve: (value: unknown) => unknown) => Promise.resolve({ data, error: null }).then(resolve),
  });
}

/**
 * Configure mockDelete to succeed.
 */
export function mockDeleteSucceeds(): void {
  mockEq.mockReturnValueOnce({
    ...chainable,
    then: (resolve: (value: unknown) => unknown) => Promise.resolve({ error: null }).then(resolve),
  });
}
