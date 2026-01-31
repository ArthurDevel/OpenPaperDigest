# ==============================================================================
# Web Dockerfile - Next.js standalone build
# ==============================================================================
# Multi-stage build for the Next.js web application.
# Uses standalone output mode for smaller production images.
#
# Responsibilities:
# - Build the Next.js application with Prisma client generation
# - Create a minimal production image using standalone output
# - Serve the web application on port 3000
# ==============================================================================

# ==============================================================================
# STAGE 1: DEPENDENCIES
# ==============================================================================
FROM node:20-alpine AS deps

WORKDIR /app

# Install dependencies required for native modules
RUN apk add --no-cache libc6-compat

# Enable corepack for pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy package files and pnpm config
COPY package.json pnpm-lock.yaml .npmrc ./
COPY prisma ./prisma/

# Install all dependencies (including devDependencies for build)
RUN pnpm install --frozen-lockfile

# ==============================================================================
# STAGE 2: BUILD
# ==============================================================================
FROM node:20-alpine AS builder

WORKDIR /app

# Enable corepack for pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Generate Prisma client
RUN pnpm exec prisma generate

# Copy prisma client to a known location for the runner stage (handles pnpm symlink structure)
RUN mkdir -p /prisma-client && \
    cp -rL node_modules/.prisma /prisma-client/ 2>/dev/null || \
    cp -rL node_modules/.pnpm/@prisma+client*/node_modules/.prisma /prisma-client/

# Build the Next.js application
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm run build

# Copy better-auth and all dependencies for migration script
RUN mkdir -p /migration-deps/@better-auth /migration-deps/@better-fetch /migration-deps/@noble /migration-deps/@standard-schema && \
    cp -rL node_modules/better-auth /migration-deps/ 2>/dev/null || cp -rL node_modules/.pnpm/better-auth*/node_modules/better-auth /migration-deps/ && \
    cp -rL node_modules/@better-auth/* /migration-deps/@better-auth/ 2>/dev/null || cp -rL node_modules/.pnpm/@better-auth*/node_modules/@better-auth/* /migration-deps/@better-auth/ && \
    cp -rL node_modules/@better-fetch/* /migration-deps/@better-fetch/ 2>/dev/null || cp -rL node_modules/.pnpm/@better-fetch*/node_modules/@better-fetch/* /migration-deps/@better-fetch/ && \
    cp -rL node_modules/@noble/* /migration-deps/@noble/ 2>/dev/null || cp -rL node_modules/.pnpm/@noble*/node_modules/@noble/* /migration-deps/@noble/ && \
    cp -rL node_modules/@standard-schema/* /migration-deps/@standard-schema/ 2>/dev/null || cp -rL node_modules/.pnpm/@standard-schema*/node_modules/@standard-schema/* /migration-deps/@standard-schema/ && \
    cp -rL node_modules/better-call /migration-deps/ 2>/dev/null || cp -rL node_modules/.pnpm/better-call*/node_modules/better-call /migration-deps/ && \
    cp -rL node_modules/defu /migration-deps/ 2>/dev/null || cp -rL node_modules/.pnpm/defu*/node_modules/defu /migration-deps/ && \
    cp -rL node_modules/jose /migration-deps/ 2>/dev/null || cp -rL node_modules/.pnpm/jose*/node_modules/jose /migration-deps/ && \
    cp -rL node_modules/kysely /migration-deps/ 2>/dev/null || cp -rL node_modules/.pnpm/kysely*/node_modules/kysely /migration-deps/ && \
    cp -rL node_modules/nanostores /migration-deps/ 2>/dev/null || cp -rL node_modules/.pnpm/nanostores*/node_modules/nanostores /migration-deps/ && \
    cp -rL node_modules/zod /migration-deps/ 2>/dev/null || cp -rL node_modules/.pnpm/zod*/node_modules/zod /migration-deps/ && \
    cp -rL node_modules/mysql2 /migration-deps/ 2>/dev/null || cp -rL node_modules/.pnpm/mysql2*/node_modules/mysql2 /migration-deps/

# ==============================================================================
# STAGE 3: PRODUCTION
# ==============================================================================
FROM node:20-alpine AS runner

WORKDIR /app

# Set production environment
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Create non-root user for security
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Copy public assets
COPY --from=builder /app/public ./public

# Copy standalone build output
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Copy Prisma client from known location
COPY --from=builder /prisma-client/.prisma ./node_modules/.prisma
COPY --from=builder /app/prisma ./prisma

# Copy migration dependencies
COPY --from=builder /migration-deps/better-auth ./node_modules/better-auth
COPY --from=builder /migration-deps/@better-auth ./node_modules/@better-auth
COPY --from=builder /migration-deps/@better-fetch ./node_modules/@better-fetch
COPY --from=builder /migration-deps/@noble ./node_modules/@noble
COPY --from=builder /migration-deps/@standard-schema ./node_modules/@standard-schema
COPY --from=builder /migration-deps/better-call ./node_modules/better-call
COPY --from=builder /migration-deps/defu ./node_modules/defu
COPY --from=builder /migration-deps/jose ./node_modules/jose
COPY --from=builder /migration-deps/kysely ./node_modules/kysely
COPY --from=builder /migration-deps/nanostores ./node_modules/nanostores
COPY --from=builder /migration-deps/zod ./node_modules/zod
COPY --from=builder /migration-deps/mysql2 ./node_modules/mysql2

# Copy migration scripts
COPY --from=builder --chown=nextjs:nodejs /app/scripts ./scripts

# Create data directory for paper JSONs
RUN mkdir -p /app/data/paperjsons && chown -R nextjs:nodejs /app/data

# Switch to non-root user
USER nextjs

# Expose port 3000
EXPOSE 3000

# Set hostname for container networking
ENV HOSTNAME="0.0.0.0"
ENV PORT=3000

# Start the server (runs migrations first, then starts Next.js)
CMD ["sh", "scripts/start.sh"]
