# =============================================================================
# Stage 1: Build React Production Frontend
# =============================================================================
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# =============================================================================
# Stage 2: Production Python Backend & Runtime
# =============================================================================
FROM python:3.10-slim AS runner

WORKDIR /app

# Install system dependencies (build-essential, curl for healthcheck, libpq for PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements and install
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r ./backend/requirements.txt

# Copy backend application source and data
COPY backend/ ./backend/

# Copy compiled frontend distribution from Stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Ensure artifacts and data directories exist
RUN mkdir -p ./backend/artifacts/backups

# Create unprivileged application user
RUN useradd -m -u 1001 tboapp && \
    chown -R tboapp:tboapp /app
USER tboapp

WORKDIR /app/backend

# Production environment defaults
ENV PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    PORT=8000 \
    HOST=0.0.0.0 \
    CORS_ORIGINS="*"

EXPOSE 8000

# Docker Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/api/health || exit 1

# Launch production server via Uvicorn with ASGI worker
CMD ["sh", "-c", "python -m uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
