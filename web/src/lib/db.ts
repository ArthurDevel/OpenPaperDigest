/**
 * Prisma Client Singleton
 *
 * Provides a single PrismaClient instance for the Next.js application.
 * - Prevents multiple client instances in development (due to hot reloading)
 * - Exports a reusable `prisma` client for database queries
 */

import { PrismaClient } from '@prisma/client';

// ============================================================================
// CONSTANTS
// ============================================================================

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined;
};

// ============================================================================
// MAIN EXPORTS
// ============================================================================

/**
 * Singleton Prisma client instance with connection pooling.
 * In development, the client is stored on globalThis to survive hot reloads.
 * In production, a new client is created once per process.
 */
export const prisma =
  globalForPrisma.prisma ??
  new PrismaClient({
    log: process.env.NODE_ENV === 'development' ? ['query', 'error', 'warn'] : ['error'],
  });

if (process.env.NODE_ENV !== 'production') {
  globalForPrisma.prisma = prisma;
}
