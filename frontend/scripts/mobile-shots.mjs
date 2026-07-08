/** Dev-only: capture readable iPhone viewport shots of specific sections. */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const SLUG = process.argv[2] || "family-demo";
const OUT = "./.shots";

const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.emulate({
  viewport: { width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
  userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
});
await page.goto(`http://localhost:3000/i/${SLUG}`, { waitUntil: "networkidle0" });
await page.evaluateHandle("document.fonts.ready");

// cover (top)
await page.screenshot({ path: `${OUT}/${SLUG}-cover.png` });

// each anchored section, scrolled to top of viewport
for (const id of ["day", "dress", "faq", "rsvp"]) {
  await page.evaluate((i) => document.getElementById(i)?.scrollIntoView(), id);
  await new Promise((r) => setTimeout(r, 350));
  await page.screenshot({ path: `${OUT}/${SLUG}-${id}.png` });
}
console.log("shots in", OUT);
await browser.close();
