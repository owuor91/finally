import { test, expect, Page, Locator } from "@playwright/test";

// Serial: tests share one backend + DB and build on each other's state
// (fresh start -> watchlist -> buy -> viz -> sell -> chat -> resilience).
test.describe.configure({ mode: "serial" });

const DEFAULT_TICKERS = [
  "AAPL",
  "GOOGL",
  "MSFT",
  "AMZN",
  "TSLA",
  "NVDA",
  "META",
  "JPM",
  "V",
  "NFLX",
];

// ---- helpers ---------------------------------------------------------------

const money = (s: string | null) => Number((s ?? "").replace(/[^0-9.-]/g, ""));

async function cash(page: Page): Promise<number> {
  return money(await page.locator("header span.text-blue").innerText());
}

async function total(page: Page): Promise<number> {
  return money(await page.locator("header span.font-bold").first().innerText());
}

// The positions table is the only table whose header contains "Avg Cost".
function positionsTable(page: Page): Locator {
  return page.locator("table", { has: page.getByText("Avg Cost") });
}

// A watchlist row is uniquely identifiable by its "Remove <T>" button.
function watchRow(page: Page, ticker: string): Locator {
  return page.getByRole("row", {
    has: page.getByRole("button", { name: `Remove ${ticker}` }),
  });
}

async function tradeViaBar(page: Page, ticker: string, qty: number, side: "Buy" | "Sell") {
  await page.getByLabel("Trade ticker").fill(ticker);
  await page.getByLabel("Trade quantity").fill(String(qty));
  await page.getByRole("button", { name: side, exact: true }).click();
}

// ---------------------------------------------------------------------------

test("1. fresh start: default watchlist, $10k cash, live streaming", async ({ page }) => {
  await page.goto("/");

  // $10,000 cash and total shown
  await expect(page.locator("header")).toContainText("$10,000.00");
  expect(await cash(page)).toBeCloseTo(10000, 1);

  // Connection dot reflects a live SSE stream
  await expect(page.locator("header").getByText("Live", { exact: true })).toBeVisible({
    timeout: 15_000,
  });

  // All 10 default tickers present in the watchlist
  for (const t of DEFAULT_TICKERS) {
    await expect(page.getByRole("button", { name: `Remove ${t}` })).toBeVisible();
  }

  // Prices are actually streaming: an AAPL price renders and then changes.
  const priceCell = watchRow(page, "AAPL").locator("td").nth(1);
  await expect(priceCell).not.toHaveText("—", { timeout: 10_000 });
  const first = await priceCell.innerText();
  await expect
    .poll(async () => priceCell.innerText(), { timeout: 15_000, intervals: [500] })
    .not.toBe(first);
});

test("2. watchlist CRUD: add PYPL then remove it", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("header").getByText("Live", { exact: true })).toBeVisible({
    timeout: 15_000,
  });

  // Add
  await page.getByLabel("Add ticker").fill("PYPL");
  await page.getByLabel("Add ticker").press("Enter");
  await expect(page.getByRole("button", { name: "Remove PYPL" })).toBeVisible();
  // ...and it starts streaming a price (not the "—" placeholder)
  await expect(watchRow(page, "PYPL").locator("td").nth(1)).not.toHaveText("—", {
    timeout: 10_000,
  });

  // Remove
  await page.getByRole("button", { name: "Remove PYPL" }).click();
  await expect(page.getByRole("button", { name: "Remove PYPL" })).toHaveCount(0);
});

test("3. buy shares: cash decreases, position + total update", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("header").getByText("Live", { exact: true })).toBeVisible({
    timeout: 15_000,
  });

  const before = await cash(page);
  await tradeViaBar(page, "AAPL", 2, "Buy");

  // Cash drops (~2 * ~$190). Poll header, which refetches after the trade.
  await expect.poll(() => cash(page), { timeout: 10_000 }).toBeLessThan(before);
  const after = await cash(page);
  expect(before - after).toBeGreaterThan(100);

  // Position row appears
  await expect(positionsTable(page).getByText("AAPL")).toBeVisible();
  await expect(positionsTable(page)).not.toContainText("No positions yet");
});

test("4. portfolio visualization: heatmap rect + P&L chart data point", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("header").getByText("Live", { exact: true })).toBeVisible({
    timeout: 15_000,
  });

  // Snapshots are recorded immediately on each trade (PLAN §7). Verify that
  // wiring directly: one trade must grow the history endpoint. (Test 3 already
  // produced snapshot #1, so after this buy there are >=2 -> the P&L line renders.)
  const histLen = async () =>
    (await page.request.get("/api/portfolio/history").then((r) => r.json())).length as number;

  const h0 = await histLen();
  const cashBefore = await cash(page);
  await tradeViaBar(page, "MSFT", 1, "Buy");
  await expect.poll(() => cash(page), { timeout: 10_000 }).toBeLessThan(cashBefore);
  await expect.poll(histLen, { timeout: 10_000 }).toBeGreaterThan(h0); // snapshot-on-trade

  // Heatmap renders a rectangle per position
  // (SVG <rect>/<path> report as "hidden" to Playwright and the charts remount
  // on every SSE tick, so assert on presence/count, not CSS visibility.)
  const heatmap = page.locator("div", {
    has: page.getByRole("heading", { name: "Positions Heatmap" }),
  });
  await expect(heatmap.getByText("No positions")).toHaveCount(0, { timeout: 10_000 });
  await expect.poll(() => heatmap.locator("svg rect").count(), { timeout: 10_000 }).toBeGreaterThan(0);

  // P&L chart has data: a recharts line path only renders with >=2 snapshots
  // (otherwise the component shows "No history yet" and no <svg>).
  const pnl = page.locator("div", {
    has: page.getByRole("heading", { name: "Portfolio Value" }),
  });
  await expect
    .poll(() => pnl.locator("svg path.recharts-curve").count(), { timeout: 10_000 })
    .toBeGreaterThan(0);
});

test("5. sell shares: cash increases, position updates/disappears", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("header").getByText("Live", { exact: true })).toBeVisible({
    timeout: 15_000,
  });

  // From test 3 we hold 2 AAPL. Sell all of them.
  await expect(positionsTable(page).getByText("AAPL")).toBeVisible();
  const before = await cash(page);

  await tradeViaBar(page, "AAPL", 2, "Sell");

  await expect.poll(() => cash(page), { timeout: 10_000 }).toBeGreaterThan(before);
  // Selling the entire position removes the row (backend deletes at qty 0).
  await expect(positionsTable(page).getByText("AAPL")).toHaveCount(0, { timeout: 10_000 });
});

test("6. AI chat (mocked): buy executes inline; bad sell surfaces error", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("header").getByText("Live", { exact: true })).toBeVisible({
    timeout: 15_000,
  });

  const before = await cash(page);

  // Successful trade via chat -> inline confirmation chip + portfolio updates
  await page.getByLabel("Chat message").fill("buy 2 AAPL");
  await page.getByRole("button", { name: "Send", exact: true }).click();

  await expect(page.getByText("Done: buy 2 AAPL.")).toBeVisible({ timeout: 15_000 });
  // The inline confirmation chip renders side/qty/ticker upper-cased.
  await expect(page.getByText("BUY 2 AAPL", { exact: true })).toBeVisible();
  await expect.poll(() => cash(page), { timeout: 10_000 }).toBeLessThan(before);
  await expect(positionsTable(page).getByText("AAPL")).toBeVisible();

  // Intentionally-failing trade -> error must surface inline, not silently drop
  await page.getByLabel("Chat message").fill("sell 999999 AAPL");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText(/Insufficient shares/i)).toBeVisible({ timeout: 15_000 });
});

test("7. SSE resilience: recovers to Live after a reload", async ({ page }) => {
  await page.goto("/");
  const dot = page.locator("header").getByText("Live", { exact: true });
  await expect(dot).toBeVisible({ timeout: 15_000 });

  // Reload interrupts the EventSource; it must auto-reconnect and go Live again.
  await page.reload();
  await expect(page.locator("header").getByText("Live", { exact: true })).toBeVisible({
    timeout: 15_000,
  });
});
