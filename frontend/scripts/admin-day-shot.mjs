/** Dev-only: screenshot the admin "The day" section (layout toggle + venue group).
 * Usage: node scripts/admin-day-shot.mjs */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const OUT = "./.shots";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.setViewport({ width: 1040, height: 1300, deviceScaleFactor: 2 });

const clickText = (sel, text) =>
  page.evaluate(
    (s, t) => {
      const el = [...document.querySelectorAll(s)].find((e) => e.textContent.trim().includes(t));
      if (el) el.click();
      return !!el;
    },
    sel,
    text,
  );

await page.goto("http://localhost:3000/admin", { waitUntil: "networkidle0" });
await page.evaluateHandle("document.fonts.ready");
await sleep(1000);
await clickText('[role="tab"], button, a', "Details");
await sleep(700);
await clickText(".MuiAccordionSummary-root", "The day");
await sleep(900);
// Centre the "Detail cells" editor so the cell list is in frame.
await page.evaluate(() => {
  const lab = [...document.querySelectorAll("p,.MuiTypography-subtitle2")].find((e) => e.textContent.trim() === "Detail cells");
  if (lab) lab.scrollIntoView({ block: "start" });
  window.scrollBy(0, -70);
});
await sleep(500);
await page.setViewport({ width: 1040, height: 1500, deviceScaleFactor: 2 });
await sleep(200);
await page.screenshot({ path: `${OUT}/admin-day-section.png` });
console.log(`shot -> ${OUT}/admin-day-section.png`);
await browser.close();
