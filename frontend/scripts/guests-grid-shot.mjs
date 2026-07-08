/** Dev-only: browser-verify the admin Guests DataGrid — that it renders with
 *  sortable/filterable columns, checkbox selection, and the bulk-action bar. Loads
 *  the admin page with the dev token in localStorage, opens the Guests tab, selects
 *  two rows, and screenshots. Point BASE at the server hosting the current build. */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const BASE = process.env.BASE || "http://localhost:3100";
const TOKEN = process.env.DEV_TOKEN || "local-dev-admin-token-change-me";
const OUT = process.env.TEMP + "/guests-grid.png";

const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.setViewport({ width: 1400, height: 1000 });

// Seed the dev admin token the same way the app's adminAuth does.
await page.goto(BASE + "/admin", { waitUntil: "domcontentloaded" });
await page.evaluate((t) => localStorage.setItem("admin_dev_token", t), TOKEN);
await page.goto(BASE + "/admin", { waitUntil: "networkidle0" });

// Open the Guests tab (label starts with "Guests").
await page.evaluate(() => {
  const tab = [...document.querySelectorAll('[role="tab"]')].find((t) => /^Guests/.test(t.textContent || ""));
  tab?.click();
});
await new Promise((r) => setTimeout(r, 800));

const hasGrid = await page.evaluate(() => !!document.querySelector(".MuiDataGrid-root"));
const colHeaders = await page.$$eval(".MuiDataGrid-columnHeaderTitle", (els) => els.map((e) => e.textContent));
const toolbar = await page.evaluate(() => !!document.querySelector(".MuiDataGrid-toolbar, [aria-label='Show filters'], button[aria-label*='filter' i]"));

// Click the first two row checkboxes to trigger the bulk-action bar.
await page.evaluate(() => {
  const boxes = [...document.querySelectorAll('.MuiDataGrid-row .MuiDataGrid-cellCheckbox input[type="checkbox"]')];
  boxes.slice(0, 2).forEach((b) => b.click());
});
await new Promise((r) => setTimeout(r, 400));
const bulkBarText = await page.evaluate(() => {
  const el = [...document.querySelectorAll("p, span")].find((e) => /\bselected$/.test((e.textContent || "").trim()));
  return el ? el.textContent.trim() : null;
});

await page.screenshot({ path: OUT, fullPage: true });
console.log(JSON.stringify({ hasGrid, colHeaders, toolbar, bulkBarText, OUT }, null, 2));
await browser.close();
