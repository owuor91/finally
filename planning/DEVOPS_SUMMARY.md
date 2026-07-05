# DevOps — Summary

**Status:** Containerization and run scripts built. Full `docker build` verification **pending** — backend `app/main.py` and the `frontend/` project don't exist yet (being built in parallel). Re-verify once they land.

## What Was Built

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage build: Node builds the frontend export, Python serves everything |
| `docker-compose.yml` | Convenience wrapper — one service, port 8000, `.env`, named volume |
| `.env.example` | Template for the three env vars (PLAN §5) |
| `scripts/start_mac.sh` / `stop_mac.sh` | macOS/Linux run helpers (idempotent) |
| `scripts/start_windows.ps1` / `stop_windows.ps1` | PowerShell equivalents |
| `db/.gitkeep` | Ensures the volume-mount target dir exists in the repo |

## Two Contract Decisions (other engineers MUST match)

These are the seams between the container and the backend code. If they don't match, the app won't serve.

1. **Static files path: `/app/static`** (built from `frontend/out`).
   The Dockerfile copies the Next.js static export into `/app/static` inside the container.
   → **Backend engineer:** mount `StaticFiles` from the directory `static` (relative to `/app`, where the backend runs). e.g. `app.mount("/", StaticFiles(directory="static", html=True), name="static")`.
   → **Frontend engineer:** `next.config` must use `output: 'export'` (produces `frontend/out`).

2. **App entrypoint: `app.main:app`.**
   The container runs `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`.
   → **Backend engineer:** the FastAPI instance must be named `app` in `backend/app/main.py`.

3. **SQLite DB path: `FINALLY_DB_PATH=/app/db/finally.db`** (set as a Dockerfile `ENV`, also in compose).
   `connection.py` resolves the DB path as `parents[3]` relative to its own file. Locally (`backend/app/db/connection.py`) that's the repo root → `<root>/db/finally.db`, correct. But the Dockerfile's `COPY backend/ ./` flattens the `backend/` segment (file lands at `/app/app/db/connection.py`), so the same math resolves to `/` → it would write `/db/finally.db`, off the volume and likely unwritable. The env override pins it to the mounted `/app/db`.
   → **Backend/db engineer:** keep honoring `FINALLY_DB_PATH` when set.

## Build / Run / Stop

```bash
cp .env.example .env        # add your OPENROUTER_API_KEY
./scripts/start_mac.sh      # builds image if missing, runs container, opens browser
./scripts/stop_mac.sh       # stops + removes container, keeps data volume
```

- `start_mac.sh --build` forces a rebuild.
- Windows: `.\scripts\start_windows.ps1 [-Build]` / `.\scripts\stop_windows.ps1`.
- Or: `docker compose up --build`.

App serves at **http://localhost:8000**. Data persists in the `finally-data` Docker volume across restarts.

## Dockerfile Details

- **Stage 1** (`node:20-slim`): `npm install && npm run build` in `frontend/` → static export at `out/`.
- **Stage 2** (`python:3.12-slim`): `uv` pulled from the official `ghcr.io/astral-sh/uv` image; `uv sync --locked --no-dev` installs from `backend/uv.lock` (production deps only); frontend export copied to `/app/static`.

Two build/runtime choices worth knowing (both changed after the first real build surfaced bugs):
- **`--locked`** (not `--frozen`) on `uv sync`: fails the build loudly if `backend/uv.lock` is out of sync with `pyproject.toml`. `--frozen` silently installs whatever the lock says and will ship an image *missing* a newly-added dependency (this actually happened — a build that raced a `litellm` add shipped without it).
- **`uv run --no-sync`** in the `CMD`: the container runs against the env baked at build time and never re-resolves/downloads at startup. Without `--no-sync`, `uv run` re-syncs on cold start — slow boot and a runtime network dependency.

## Verification Status

**Full end-to-end `docker build` + run: PASSED ✅** (2026-07-05, Docker Desktop 29.1.3).

- Image builds through both stages clean (`docker build -t finally .`).
- `docker run -e LLM_MOCK=true -v <vol>:/app/db finally`: healthy in ~1s. `curl /api/health` → `{"status":"ok"}`, `curl /` → 200 (frontend `index.html`).
- **DB path fix verified**: `finally.db` is written to `/app/db/finally.db` (on the mounted volume); nothing stray at `/db`. A trade (`AAPL` x2, cash 10000→9619.84) survived a container stop/restart against the same volume — persistence confirmed.
- **`litellm` baked into the image venv** (confirmed present; no runtime download in logs after the `--locked` fix).
- Shell scripts: `bash -n` syntax-checked. ✅
- Test container + volume cleaned up; `finally:latest` image (866MB) retained.
