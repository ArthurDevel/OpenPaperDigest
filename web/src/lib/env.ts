/**
 * Environment Variable Validation
 *
 * Uses Zod to validate and type environment variables at runtime.
 * - Throws an error at startup if required variables are missing or invalid
 * - Exports a typed `env` object for safe access throughout the application
 */

import { z } from 'zod';

// ============================================================================
// SCHEMA
// ============================================================================

const envSchema = z.object({
  // Database connection string for Prisma
  DATABASE_URL: z.string().url(),

  // Password for HTTP Basic authentication on admin endpoints
  ADMIN_BASIC_PASSWORD: z.string().min(1),

  // Node environment (development, production, or test)
  NODE_ENV: z.enum(['development', 'production', 'test']).default('development'),
});

// ============================================================================
// MAIN EXPORTS
// ============================================================================

/**
 * Validated environment variables object.
 * Throws a ZodError at import time if validation fails.
 */
export const env = envSchema.parse(process.env);

/**
 * Type for the validated environment object.
 */
export type Env = z.infer<typeof envSchema>;
