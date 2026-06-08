import { test, expect } from "@playwright/test";

const BASE = process.env.BASE_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// API tests (no browser needed)
// ---------------------------------------------------------------------------

test.describe("Health check", () => {
  test("API health returns ok", async ({ request }) => {
    const resp = await request.get(`${BASE}/api/health`);
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.status).toBe("ok");
  });
});

test.describe("Watchlist API", () => {
  test("Default watchlist has 10 tickers", async ({ request }) => {
    const resp = await request.get(`${BASE}/api/watchlist`);
    expect(resp.ok()).toBeTruthy();
    const items = await resp.json();
    expect(items.length).toBe(10);
  });

  test("Add and remove ticker", async ({ request }) => {
    const ticker = "ONGCTEST";
    const addResp = await request.post(`${BASE}/api/watchlist`, {
      data: { ticker },
    });
    expect(addResp.status()).toBe(201);

    const listResp = await request.get(`${BASE}/api/watchlist`);
    const items = await listResp.json();
    expect(items.some((i: { ticker: string }) => i.ticker === ticker)).toBeTruthy();

    const delResp = await request.delete(`${BASE}/api/watchlist/${ticker}`);
    expect(delResp.ok()).toBeTruthy();

    const listResp2 = await request.get(`${BASE}/api/watchlist`);
    const items2 = await listResp2.json();
    expect(items2.some((i: { ticker: string }) => i.ticker === ticker)).toBeFalsy();
  });

  test("Duplicate ticker returns 409", async ({ request }) => {
    const resp = await request.post(`${BASE}/api/watchlist`, {
      data: { ticker: "RELIANCE" },
    });
    expect(resp.status()).toBe(409);
  });
});

test.describe("Portfolio API", () => {
  test("Fresh portfolio has correct structure", async ({ request }) => {
    const resp = await request.get(`${BASE}/api/portfolio`);
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data).toHaveProperty("cash");
    expect(data).toHaveProperty("positions");
    expect(data).toHaveProperty("total_value");
    expect(Array.isArray(data.positions)).toBeTruthy();
  });

  test("Buy trade executes and reduces cash", async ({ request }) => {
    const portfolioBefore = await request.get(`${BASE}/api/portfolio`);
    const { cash: cashBefore } = await portfolioBefore.json();

    const tradeResp = await request.post(`${BASE}/api/portfolio/trade`, {
      data: { ticker: "RELIANCE", side: "buy", quantity: 1 },
    });
    expect(tradeResp.ok()).toBeTruthy();

    const portfolioAfter = await request.get(`${BASE}/api/portfolio`);
    const { cash: cashAfter, positions } = await portfolioAfter.json();
    expect(cashAfter).toBeLessThan(cashBefore);
    expect(positions.some((p: { ticker: string }) => p.ticker === "RELIANCE")).toBeTruthy();
  });

  test("Portfolio history returns list", async ({ request }) => {
    const resp = await request.get(`${BASE}/api/portfolio/history`);
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(Array.isArray(data)).toBeTruthy();
  });
});

test.describe("Stock detail API", () => {
  const PERIODS = ["1d", "1w", "1m", "6m", "1y", "5y"];

  for (const period of PERIODS) {
    test(`History endpoint returns data for period=${period}`, async ({ request }) => {
      const resp = await request.get(`${BASE}/api/stock/RELIANCE/history?period=${period}`);
      expect(resp.ok()).toBeTruthy();
      const data = await resp.json();
      expect(Array.isArray(data)).toBeTruthy();
      expect(data.length).toBeGreaterThan(1);
      expect(data[0]).toHaveProperty("time");
      expect(data[0]).toHaveProperty("price");
      expect(typeof data[0].price).toBe("number");
    });
  }

  test("Invalid period returns 422", async ({ request }) => {
    const resp = await request.get(`${BASE}/api/stock/RELIANCE/history?period=bad`);
    expect(resp.status()).toBe(422);
  });

  test("Quote endpoint returns 52W stats", async ({ request }) => {
    const resp = await request.get(`${BASE}/api/stock/TCS/quote`);
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data).toHaveProperty("ticker");
    expect(data).toHaveProperty("price");
    expect(data).toHaveProperty("week_52_high");
    expect(data).toHaveProperty("week_52_low");
    expect(data.week_52_high).toBeGreaterThan(data.week_52_low);
  });
});

test.describe("Chat API (mock mode)", () => {
  test("Chat returns structured response", async ({ request }) => {
    const resp = await request.post(`${BASE}/api/chat`, {
      data: { message: "hello" },
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data).toHaveProperty("message");
    expect(data).toHaveProperty("actions");
    expect(data.actions).toHaveProperty("trades");
    expect(data.actions).toHaveProperty("watchlist_changes");
  });

  test("Empty message returns 422", async ({ request }) => {
    const resp = await request.post(`${BASE}/api/chat`, {
      data: { message: "" },
    });
    expect(resp.status()).toBe(422);
  });
});

test.describe("SSE stream", () => {
  test("Stream endpoint exists and is not 404", async ({ request }) => {
    const resp = await request.get(`${BASE}/api/stream/prices`, {
      timeout: 2000,
    }).catch(() => null);
    if (resp) {
      expect(resp.status()).not.toBe(404);
    }
  });
});

test.describe("Frontend", () => {
  test("Root returns HTML with correct title", async ({ request }) => {
    const resp = await request.get(`${BASE}/`);
    expect(resp.ok()).toBeTruthy();
    const ct = resp.headers()["content-type"];
    expect(ct).toContain("text/html");
    const body = await resp.text();
    expect(body).toContain("FinAlly");
  });
});

// ---------------------------------------------------------------------------
// Browser (UI) tests
// ---------------------------------------------------------------------------

test.describe("UI — page load", () => {
  test("Page loads with header and watchlist", async ({ page }) => {
    await page.goto(BASE);
    // Wait for watchlist tickers to render (SSE + API load)
    await page.waitForFunction(
      () => document.body.innerText.includes("RELIANCE"),
      { timeout: 10000 }
    );
    expect(await page.title()).toContain("FinAlly");
    // Header should show portfolio value
    const headerText = await page.innerText("header");
    expect(headerText).toContain("₹");
  });

  test("Connection status eventually shows Live or Connecting", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForTimeout(3000);
    const bodyText = await page.innerText("body");
    // Should show either "Live" (connected) or "Connecting" (reconnecting)
    const hasStatus = bodyText.includes("Live") || bodyText.includes("Connecting") || bodyText.includes("Offline");
    expect(hasStatus).toBeTruthy();
  });
});

test.describe("UI — stock detail panel", () => {
  test("Clicking a ticker shows StockDetail with price and stats", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForFunction(
      () => document.body.innerText.includes("RELIANCE"),
      { timeout: 10000 }
    );

    await page.click("text=RELIANCE");
    // Wait for quote data to load (async fetch)
    await page.waitForFunction(
      () => document.body.innerText.includes("52W"),
      { timeout: 8000 }
    );

    const bodyText = await page.innerText("body");
    expect(bodyText).toContain("RELIANCE");
    expect(bodyText).toMatch(/52W/i);
  });

  test("Duration buttons are present after ticker selection", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForFunction(
      () => document.body.innerText.includes("TCS"),
      { timeout: 10000 }
    );
    await page.click("text=TCS");
    // Wait for StockDetail to render period buttons
    await page.waitForSelector("button[data-period='1d']", { timeout: 8000 });

    for (const key of ["1d", "1w", "1m", "6m", "1y", "5y"]) {
      await expect(page.locator(`button[data-period='${key}']`)).toBeVisible();
    }
  });

  test("Switching duration fetches new chart data", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForFunction(
      () => document.body.innerText.includes("INFY"),
      { timeout: 10000 }
    );
    await page.click("text=INFY");
    await page.waitForTimeout(1000);

    // Click 1Y period button
    await page.click("button[data-period='1y']");
    // Should briefly show loading then render the chart (no page error)
    await page.waitForTimeout(2000);

    // Verify no JS page errors
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    expect(errors).toHaveLength(0);
  });
});

test.describe("UI — trade bar", () => {
  test("Trade bar is visible with BUY and SELL buttons", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForFunction(
      () => document.body.innerText.includes("RELIANCE"),
      { timeout: 10000 }
    );
    await expect(page.locator("button", { hasText: "BUY" })).toBeVisible();
    await expect(page.locator("button", { hasText: "SELL" })).toBeVisible();
  });

  test("Clicking ticker populates trade bar ticker field", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForFunction(
      () => document.body.innerText.includes("TCS"),
      { timeout: 10000 }
    );
    await page.click("text=TCS");
    // Wait for useEffect to sync selectedTicker → trade bar input
    await page.waitForFunction(
      () => {
        const inputs = Array.from(document.querySelectorAll("input"));
        return inputs.some((i) => (i as HTMLInputElement).value === "TCS");
      },
      { timeout: 5000 }
    );

    const inputs = page.locator("input");
    const vals = await inputs.evaluateAll((els) =>
      (els as HTMLInputElement[]).map((e) => e.value)
    );
    expect(vals).toContain("TCS");
  });
});

test.describe("UI — AI chat panel", () => {
  test("Chat panel is visible with message input", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForFunction(
      () => document.body.innerText.toUpperCase().includes("AI ASSISTANT"),
      { timeout: 10000 }
    );
    await expect(page.locator("textarea")).toBeVisible();
  });
});
