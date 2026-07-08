/** Dev-only: screenshot the "THE DAY" card at mobile + desktop widths.
 * Usage: node scripts/daycard-shots.mjs <label> [slug]  (label → filename suffix) */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const LABEL = process.argv[2] || "combined";
const SLUG = process.argv[3] || "plusone-demo";
const OUT = "./.shots";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"] });

async function shot(width, tag) {
  const page = await browser.newPage();
  await page.setViewport({ width, height: 1100, deviceScaleFactor: 2 });
  await page.goto(`http://localhost:3000/i/${SLUG}`, { waitUntil: "networkidle0" });
  await page.evaluateHandle("document.fonts.ready");
  await page.evaluate(() => document.getElementById("day")?.scrollIntoView({ block: "center" }));
  await sleep(400);
  const el = await page.$("#day");
  await el.screenshot({ path: `${OUT}/daycard-${LABEL}-${tag}.png` });
  console.log(`shot -> ${OUT}/daycard-${LABEL}-${tag}.png`);
  await page.close();
}

await shot(430, "mobile");
await shot(960, "desktop");
await browser.close();
