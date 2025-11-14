ARG CONTAINERPORT_API
# Stage 1: Build the Next.js frontend
FROM node:18-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund

# Set build-time env after deps install so changing it doesn't invalidate the npm cache layer
ARG CONTAINERPORT_API
ARG NEXT_PUBLIC_UMAMI_URL
ARG NEXT_PUBLIC_UMAMI_WEBSITE_ID

ENV NEXT_PUBLIC_CONTAINERPORT_API=$CONTAINERPORT_API
ENV NEXT_PUBLIC_UMAMI_URL=$NEXT_PUBLIC_UMAMI_URL
ENV NEXT_PUBLIC_UMAMI_WEBSITE_ID=$NEXT_PUBLIC_UMAMI_WEBSITE_ID

COPY frontend ./
RUN npm run build

# Stage 2: Setup Python environment and install dependencies
FROM python:3.10-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    npm \
    default-libmysqlclient-dev \
    netcat-openbsd \
    pkg-config \
    build-essential \
    libmagic1 \
    libgl1 \
    libglib2.0-0 \
    poppler-utils \
    git \
    cmake \
    wget \
    && rm -rf /var/lib/apt/lists/*

    #libgl1-mesa-glx \

# Copy Python requirements and install packages
# Note: scipy is now a direct dependency
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download and cache the layout model to a non-volume-mounted path in a single layer
# RUN mkdir -p /models && \
    #wget -O /models/publaynet_config.yml "https://www.dropbox.com/s/f3b12qc4hc0yh4m/config.yml?dl=1" && \
    #wget -O /models/publaynet_model.pth "https://www.dropbox.com/s/dgy9c10wykk4lq4/model_final.pth?dl=1"

# Copy the built frontend from the builder stage first so this layer stays cached when backend-only files change
COPY --from=frontend-builder /app/frontend/.next ./frontend/.next
COPY --from=frontend-builder /app/frontend/public ./frontend/public
COPY --from=frontend-builder /app/frontend/node_modules ./frontend/node_modules

# Copy application code
COPY . .

# Copy entrypoint script to a location that won't be overwritten by a volume mount
COPY entrypoint.sh /usr/local/bin/
# Make entrypoint script executable
RUN chmod +x /usr/local/bin/entrypoint.sh

# Expose ports for frontend only, as backend is accessed via the proxy.
EXPOSE ${CONTAINERPORT_FRONTEND:-3000}

# Set the entrypoint script
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# Start both backend and frontend services directly
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${CONTAINERPORT_API:-8000} & cd frontend && PORT=${CONTAINERPORT_FRONTEND:-3000} npm start"]