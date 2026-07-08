/** Dev-only: browser-verify the admin Overview (Summary) tab — stat cards, the RSVP
 *  status donut, the confirmed-vs-expected head-count bar, the by-side bar, and the
 *  per-question breakdown bars. Writes a full-page shot plus close-up clips of the two
 *  chart rows. Point BASE at the server hosting the current build. */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const BASE = process.env.BASE || "http://localhost:3000";
const TOKEN = process.env.DEV_TOKEN || "local-dev-admin-token-change-me";
const DIR = (process.env.TEMP || "/tmp").replace(/\\/g, "/");

const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 1200, deviceScaleFactor: 2 });

await page.goto(BASE + "/admin", { waitUntil: "domcontentloaded" });
await page.evaluate((t) => localStorage.setItem("admin_dev_token", t), TOKEN);
await page.goto(BASE + "/admin", { waitUntil: "networkidle0" });
await page.evaluate(() => {
  const tab = [...document.querySelectorAll('[role="tab"]')].find((t) => /Overview|Summary/i.test(t.textContent || ""));
  tab?.click();
});
await new Promise((r) => setTimeout(r, 1400));

const cardTitles = await page.$$eval(".MuiCardContent-root .MuiTypography-subtitle1", (els) => els.map((e) => e.textContent));

await page.screenshot({ path: DIR + "/overview-full.png", fullPage: true });

// Close-up of a chart row, found by the flex Box that holds a card with the given title.
async function clipRow(title, out) {
  const box = await page.evaluate((t) => {
    const sub = [...document.querySelectorAll(".MuiTypography-subtitle1")].find((e) => (e.textContent || "").trim() === t);
    const card = sub?.closest(".MuiCard-root");
    const row = card?.parentElement;
    if (!row) return null;
    const r = row.getBoundingClientRect();
    return { x: r.x, y: r.y + window.scrollY, width: r.width, height: r.height };
  }, title);
  if (!box) return false;
  await page.screenshot({
    path: out,
    clip: { x: Math.max(0, box.x - 8), y: Math.max(0, box.y - 8), width: box.width + 16, height: box.height + 16 },
  });
  return true;
}

const a = await clipRow("RSVP status", DIR + "/overview-charts.png");
const b = await clipRow("Any dietary needs?", DIR + "/overview-breakdowns.png");

console.log(JSON.stringify({ cardTitles, clips: { charts: a, breakdowns: b }, DIR }, null, 2));
await browser.close();
