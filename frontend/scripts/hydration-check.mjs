/** Dev-only: load the invite page in a clean (extension-free) Chrome and report any
 * console errors / hydration warnings. Usage: node scripts/hydration-check.mjs [slug] */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const SLUG = process.argv[2] || "plusone-demo";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"] });
const page = await browser.newPage();

const msgs = [];
page.on("console", (m) => {
  const t = m.type();
  if (t === "error" || t === "warning") msgs.push(`[${t}] ${m.text()}`);
});
page.on("pageerror", (e) => msgs.push(`[pageerror] ${e.message}`));

await page.goto(`http://localhost:3000/i/${SLUG}`, { waitUntil: "networkidle0" });
await sleep(1200);

const hyd = msgs.filter((m) => /hydrat|did not match|tree hydrated/i.test(m));
console.log(`total console errors/warnings: ${msgs.length}`);
console.log(`hydration-related: ${hyd.length}`);
for (const m of msgs.slice(0, 12)) console.log("  -", m.slice(0, 160));
await browser.close();
