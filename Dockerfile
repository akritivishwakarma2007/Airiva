# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000 \
    APP_ENV=production

# Install essential system utilities for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create a dedicated non-root application user
RUN useradd -m -u 1000 -s /bin/bash appuser

WORKDIR /app

# Install production Python dependencies (no Playwright/Chromium in this runtime image)
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code with non-root ownership
COPY --chown=appuser:appuser . /app/

# Ensure both apix and Airiva package namespace paths resolve cleanly
RUN if [ ! -d /app/apix ] && [ -d /app/Airiva ]; then ln -s /app/Airiva /app/apix; fi && \
    if [ ! -d /app/Airiva ] && [ -d /app/apix ]; then ln -s /app/apix /app/Airiva; fi

# Switch to non-root user
USER appuser

# Expose $PORT (default 8000 or platform provided)
EXPOSE $PORT

# Container healthcheck against /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Start FastAPI application
CMD uvicorn apix.api.main:app --host 0.0.0.0 --port $PORT
