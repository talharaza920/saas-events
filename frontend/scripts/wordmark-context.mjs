/** Dev-only: screenshot the cover hero (wordmark in context, spin running) on a
 * phone viewport to sanity-check the change. Usage: node scripts/wordmark-context.mjs */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const SLUG = process.argv[2] || "plusone-demo";
const OUT = "./.shots";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.emulate({
  viewport: { width: 390, height: 844, deviceScaleFactor: 3, isMobile: true, hasTouch: true },
  userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
});
await page.goto(`http://localhost:3000/i/${SLUG}`, { waitUntil: "networkidle0" });
await page.evaluateHandle("document.fonts.ready");
await sleep(500);
await page.screenshot({ path: `${OUT}/wordmark-context.png` });
console.log(`shot -> ${OUT}/wordmark-context.png`);
await browser.close();
