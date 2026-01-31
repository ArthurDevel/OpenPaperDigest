#!/bin/sh
# ==============================================================================
# Startup script - runs BetterAuth migrations then starts Next.js server
# ==============================================================================

echo "Running BetterAuth database migrations..."
node /app/scripts/migrate.mjs

echo "Starting Next.js server..."
exec node server.js
