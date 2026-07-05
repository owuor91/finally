# syntax=docker/dockerfile:1

# ---- Stage 1: build the Next.js static export ----
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/ ./
RUN npm install && npm run build
# Next.js `output: 'export'` writes the static site to ./out

# ---- Stage 2: Python backend that also serves the static frontend ----
FROM python:3.12-slim AS backend
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app
COPY backend/ ./
# Production install (no dev deps). --locked fails the build if uv.lock is out of
# sync with pyproject.toml, rather than silently shipping a missing dependency.
RUN uv sync --locked --no-dev

# Frontend export lands at /app/static — backend serves StaticFiles from here
COPY --from=frontend /app/frontend/out ./static

# connection.py resolves the db path relative to its own location; the `COPY backend/ ./`
# flatten shifts that resolution, so pin the path explicitly to the volume mount.
ENV FINALLY_DB_PATH=/app/db/finally.db
EXPOSE 8000
# --no-sync: run against the env baked at build time; never resync/download at startup.
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
