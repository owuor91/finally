import { defineConfig, devices } from "@playwright/test";
import path from "path";

// Fresh throwaway DB per run so state is deterministic (fresh $10k, empty portfolio).
const DB = path.join(__dirname, ".tmp", "e2e.db");
const BACKEND = path.join(__dirname, "..", "backend");

// When RUN_AGAINST_RUNNING=1, don't boot a server — hit an already-running app
// (e.g. the docker-compose.test.yml container). Otherwise Playwright boots the
// backend directly with the pre-built static frontend it serves from backend/static.
const external = process.env.RUN_AGAINST_RUNNING === "1";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.BASE_URL ?? "http://127.0.0.1:8000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: external
    ? undefined
    : {
        command: `bash -c "rm -f '${DB}' && LLM_MOCK=true FINALLY_DB_PATH='${DB}' uv run --no-sync uvicorn app.main:app --host 127.0.0.1 --port 8000"`,
        cwd: BACKEND,
        url: "http://127.0.0.1:8000/api/health",
        timeout: 60_000,
        reuseExistingServer: false,
      },
});
