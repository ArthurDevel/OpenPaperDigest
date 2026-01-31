#!/bin/sh
# ==============================================================================
# Startup script - starts Next.js server and runs BetterAuth migrations
# ==============================================================================

echo "Starting Next.js server..."
node server.js &
SERVER_PID=$!

# Wait for server to be ready
echo "Waiting for server to be ready..."
until curl -s http://localhost:3000/api/health > /dev/null 2>&1; do
  sleep 1
done

# Run migrations via API endpoint
echo "Running BetterAuth database migrations..."
MIGRATE_RESULT=$(curl -s -X POST http://localhost:3000/api/migrate)
echo "Migration result: $MIGRATE_RESULT"

# Keep the server running in foreground
wait $SERVER_PID
