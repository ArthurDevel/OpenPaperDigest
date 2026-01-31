// ==============================================================================
// BetterAuth Database Migration Script
// ==============================================================================
// Uses BetterAuth's built-in migration system.
// Executed before the Next.js server starts.
// ==============================================================================

import { getMigrations } from "better-auth/db/migration";
import { createPool } from 'mysql2/promise';

const AUTH_MYSQL_URL = process.env.AUTH_MYSQL_URL;

if (!AUTH_MYSQL_URL) {
  console.error('AUTH_MYSQL_URL environment variable is not set');
  process.exit(1);
}

const authDbPool = createPool({
  uri: AUTH_MYSQL_URL,
  waitForConnections: true,
  connectionLimit: 10,
});

// Auth config matching server_auth.ts
const authConfig = {
  database: authDbPool,
  plugins: [],
};

async function runMigrations() {
  try {
    const { toBeCreated, toBeAdded, runMigrations } = await getMigrations(authConfig);

    if (toBeCreated.length > 0) {
      console.log('Tables to create:', toBeCreated);
    }
    if (toBeAdded.length > 0) {
      console.log('Fields to add:', toBeAdded);
    }

    if (toBeCreated.length > 0 || toBeAdded.length > 0) {
      await runMigrations();
      console.log('BetterAuth migrations completed successfully');
    } else {
      console.log('BetterAuth database is up to date');
    }
  } catch (error) {
    console.error('Migration error:', error.message);
    process.exit(1);
  } finally {
    await authDbPool.end();
  }
}

runMigrations();
