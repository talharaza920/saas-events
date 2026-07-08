/** Dev-only: drive the RSVP flow to the details step on mobile, check the mascot
 * badge stays square, and screenshot. Usage: node scripts/mobile-rsvp.mjs [slug] */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const SLUG = process.argv[2] || "family-demo";
const OUT = "./.shots";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.emulate({
  viewport: { width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
  userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
});
await page.goto(`http://localhost:3000/i/${SLUG}`, { waitUntil: "networkidle0" });
await page.evaluateHandle("document.fonts.ready");

const clickText = (sel, text) =>
  page.evaluate(
    (s, t) => {
      const el = [...document.querySelectorAll(s)].find((e) => e.textContent.includes(t));
      if (el) el.click();
      return !!el;
    },
    sel,
    text,
  );

await page.evaluate(() => document.getElementById("rsvp")?.scrollIntoView());
await sleep(300);
await clickText('[role="button"]', "Joyfully accepts");
await sleep(200);
// advance until we reach the "Help us plan" details step (max 3 hops)
for (let i = 0; i < 3; i++) {
  const onDetails = await page.evaluate(() => document.body.textContent.includes("Help us plan"));
  if (onDetails) break;
  await clickText("button", "Next");
  await sleep(300);
}

// measure the badge inside the rsvp card
const badge = await page.evaluate(() => {
  const card = document.getElementById("rsvp");
  // the mascot badge ring is the closest div to the cat glyph's <polygon> ears
  const ear = card?.querySelector("svg polygon");
  const ring = ear?.closest("div");
  const b = ring?.getBoundingClientRect();
  return b ? { w: Math.round(b.width), h: Math.round(b.height) } : null;
});
console.log("mascot badge box:", badge, badge && Math.abs(badge.w - badge.h) <= 1 ? "SQUARE ✓" : "NOT SQUARE ✗");

await page.screenshot({ path: `${OUT}/${SLUG}-rsvp-details.png` });
console.log(`shot -> ${OUT}/${SLUG}-rsvp-details.png`);
await browser.close();
