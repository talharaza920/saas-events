/** Dev-only: render old vs fixed wordmark arcs (alphabetic baseline) with a guide
 *  circle + centre dot, to eyeball concentricity. Chrome === Safari here since no
 *  baseline attribute is used. */
import puppeteer from "puppeteer-core";
const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const OUT = process.env.TEMP + "/wordmark-fix.png";
const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.goto("http://localhost:3000/", { waitUntil: "networkidle0" });
await page.evaluate("document.fonts.ready");

function svg(title, topD, botD, baseline) {
  const bl = baseline ? `dominant-baseline="${baseline}"` : "";
  return `<div style="display:inline-block;text-align:center;font:14px sans-serif">
    <div>${title}</div>
    <svg viewBox="0 0 200 200" width="220" height="220" style="border:1px solid #ccc">
      <defs><path id="t_${title}" d="${topD}" fill="none"/><path id="b_${title}" d="${botD}" fill="none"/></defs>
      <circle cx="100" cy="100" r="70" fill="none" stroke="#e0a" stroke-dasharray="3 3"/>
      <circle cx="100" cy="100" r="2" fill="#e0a"/>
      <text font-family='var(--font-display),"Baloo 2"' font-weight="700" font-size="22" letter-spacing="1.5" ${bl}>
        <textPath href="#t_${title}" startOffset="50%" text-anchor="middle">Ever after</textPath></text>
      <text font-family='var(--font-display),"Baloo 2"' font-weight="700" font-size="22" letter-spacing="1.5" ${bl}>
        <textPath href="#b_${title}" startOffset="50%" text-anchor="middle">Ever after</textPath></text>
    </svg></div>`;
}
await page.evaluate((html) => { document.body.innerHTML = `<div style="display:flex;gap:16px;padding:16px;background:#fff">${html}</div>`; },
  svg("OLD-alphabetic(Safari)", "M30,100 a70,70 0 1,1 140,0", "M30,100 a70,70 0 0,0 140,0", "") +
  svg("OLD-central(Chrome)", "M30,100 a70,70 0 1,1 140,0", "M30,100 a70,70 0 0,0 140,0", "central") +
  svg("FIX-geometric", "M36,100 a64,64 0 1,1 128,0", "M24,100 a76,76 0 0,0 152,0", ""));
await page.evaluate("document.fonts.ready");
await page.screenshot({ path: OUT });
console.log(OUT);
await browser.close();
