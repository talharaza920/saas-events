/** Dev-only: screenshot the rotating wordmark with the spin frozen (reduced-motion)
 * so both text bands' orientation is visible. Usage: node scripts/wordmark-diagnose.mjs */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const SLUG = process.argv[2] || "plusone-demo";
const OUT = "./.shots";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.setViewport({ width: 760, height: 900, deviceScaleFactor: 3 });
await page.emulateMediaFeatures([{ name: "prefers-reduced-motion", value: "reduce" }]);
await page.goto(`http://localhost:3000/i/${SLUG}`, { waitUntil: "networkidle0" });
await page.evaluateHandle("document.fonts.ready");
await sleep(400);

const svg = await page.$("#cover svg");
await svg.screenshot({ path: `${OUT}/wordmark-frozen.png` });
console.log(`shot -> ${OUT}/wordmark-frozen.png`);
await browser.close();
