# ==============================================================================
# Web Dockerfile - Next.js standalone build
# ==============================================================================
# Multi-stage build for the Next.js web application.
# Uses standalone output mode for smaller production images.
#
# Responsibilities:
# - Build the Next.js application
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

# NEXT_PUBLIC_* vars must be available at build time (Next.js inlines them into client JS)
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ARG NEXT_PUBLIC_SITE_URL
ARG NEXT_PUBLIC_UMAMI_URL
ARG NEXT_PUBLIC_UMAMI_WEBSITE_ID

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

# Create non-root user for security
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Copy public assets
COPY --from=builder /app/public ./public

# Copy standalone build output
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Install migration dependencies
RUN corepack enable && corepack prepare pnpm@latest --activate && \
    pnpm add better-auth mysql2

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
