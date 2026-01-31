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


# ==============================================================================
# STAGE 3: PRODUCTION
# ==============================================================================
FROM node:20-alpine AS runner

WORKDIR /app

# Set production environment
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Install curl for health checks and migration trigger
RUN apk add --no-cache curl

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

# Copy startup script
COPY --from=builder --chown=nextjs:nodejs /app/scripts/start.sh ./scripts/start.sh

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
