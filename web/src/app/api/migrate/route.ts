import { NextResponse } from "next/server";
import { getMigrations } from "better-auth/db";
import { createPool } from "mysql2/promise";

// This endpoint runs BetterAuth database migrations
// Called by the startup script before the server is fully ready
export async function POST() {
  const AUTH_MYSQL_URL = process.env.AUTH_MYSQL_URL;

  if (!AUTH_MYSQL_URL) {
    return NextResponse.json(
      { error: "AUTH_MYSQL_URL not configured" },
      { status: 500 }
    );
  }

  const pool = createPool({
    uri: AUTH_MYSQL_URL,
    waitForConnections: true,
    connectionLimit: 1,
  });

  try {
    const authConfig = {
      database: pool,
    };

    const { toBeCreated, toBeAdded, runMigrations } =
      await getMigrations(authConfig);

    if (toBeCreated.length === 0 && toBeAdded.length === 0) {
      await pool.end();
      return NextResponse.json({ message: "Database is up to date" });
    }

    await runMigrations();
    await pool.end();

    return NextResponse.json({
      message: "Migrations completed",
      tablesCreated: toBeCreated.map((t) => t.table),
      fieldsAdded: toBeAdded.map((t) => t.table),
    });
  } catch (error) {
    await pool.end();
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
