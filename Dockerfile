# Stage 1: Build Next.js frontend
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --prefer-offline 2>/dev/null || npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend
FROM python:3.12-slim AS final

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app/backend

# Install Python dependencies (lockfile preferred, fallback to unlock for CI)
COPY backend/pyproject.toml backend/uv.lock* ./
RUN uv sync --no-dev --locked 2>/dev/null || uv sync --no-dev

# Copy backend source (includes schema/ subdirectory)
COPY backend/ .

# Copy frontend static export
COPY --from=frontend-builder /app/frontend/out /app/static

# Create db directory
RUN mkdir -p /app/db

EXPOSE 8000

ENV DB_PATH=/app/db/finally.db
ENV STATIC_DIR=/app/static

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
