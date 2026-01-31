/**
 * Authentication Configuration
 *
 * Re-exports the BetterAuth server instance for use in API routes.
 * - Provides a clean import path: `import { auth } from '@/lib/auth'`
 * - All configuration is in server_auth.ts
 */

export { auth } from './server_auth';
