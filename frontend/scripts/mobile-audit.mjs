/**
 * Dev-only mobile QA: drives the system Chrome (no download) to emulate an
 * iPhone, report any element that overflows the viewport width, and screenshot
 * each invite section. Usage: node scripts/mobile-audit.mjs [slug]
 */
import puppeteer from "puppeteer-core";

const CHROME =
  process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const SLUG = process.argv[2] || "family-demo";
const URL = `http://localhost:3000/i/${SLUG}`;
const OUT = "./.shots";

const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.emulate({
  viewport: { width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
  userAgent:
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
});
await page.goto(URL, { waitUntil: "networkidle0" });
await page.evaluateHandle("document.fonts.ready");

const report = await page.evaluate(() => {
  const vw = document.documentElement.clientWidth;
  const overflow = [];
  for (const el of document.querySelectorAll("*")) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (r.right > vw + 1 || r.left < -1) {
      overflow.push({
        tag: el.tagName.toLowerCase(),
        cls: (el.className && el.className.toString().slice(0, 40)) || "",
        left: Math.round(r.left),
        right: Math.round(r.right),
        text: (el.textContent || "").trim().slice(0, 30),
      });
    }
  }
  return {
    viewport: vw,
    scrollWidth: document.documentElement.scrollWidth,
    hasHScroll: document.documentElement.scrollWidth > vw,
    overflow: overflow.slice(0, 20),
  };
});

console.log(JSON.stringify(report, null, 2));

await page.screenshot({ path: `${OUT}/${SLUG}-full.png`, fullPage: true });
console.log(`full-page -> ${OUT}/${SLUG}-full.png`);

await browser.close();
