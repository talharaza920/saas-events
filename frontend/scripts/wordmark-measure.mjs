/** Dev-only: measure where curved wordmark text actually lands, to calibrate a
 *  baseline-independent (pure-geometry) centering. Runs in real Chrome against
 *  the running Next app so the actual --font-display metrics are used. */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.goto("http://localhost:3000/", { waitUntil: "networkidle0" });
await page.evaluate("document.fonts.ready");

const result = await page.evaluate(() => {
  const NS = "http://www.w3.org/2000/svg";
  const FONT = getComputedStyle(document.body).getPropertyValue("--font-display") || "sans-serif";
  const out = {};

  function mk() {
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 200 200");
    svg.setAttribute("width", "200");
    svg.setAttribute("height", "200");
    svg.style.position = "fixed";
    svg.style.left = "0";
    svg.style.top = "0";
    document.body.appendChild(svg);
    return svg;
  }
  function styleText(t) {
    t.setAttribute("font-family", FONT);
    t.setAttribute("font-weight", "700");
    t.setAttribute("font-size", "22");
    t.setAttribute("letter-spacing", "1.5");
  }

  // 1) horizontal baseline at y=100: measure alphabetic glyph band vs baseline
  {
    const svg = mk();
    const t = document.createElementNS(NS, "text");
    styleText(t);
    t.setAttribute("x", "10");
    t.setAttribute("y", "100");
    t.textContent = "Ever after";
    svg.appendChild(t);
    const b = t.getBBox();
    out.horizontal = { top: b.y, bottom: b.y + b.height, center: b.y + b.height / 2, baseline: 100 };
    svg.remove();
  }

  // 2) arc text on top & bottom semicircles at r=70, alphabetic (default)
  function arc(dPath, which, dy) {
    const svg = mk();
    const defs = document.createElementNS(NS, "defs");
    const p = document.createElementNS(NS, "path");
    p.setAttribute("id", "p_" + which);
    p.setAttribute("d", dPath);
    p.setAttribute("fill", "none");
    defs.appendChild(p);
    svg.appendChild(defs);
    const t = document.createElementNS(NS, "text");
    styleText(t);
    const tp = document.createElementNS(NS, "textPath");
    tp.setAttribute("href", "#p_" + which);
    tp.setAttribute("startOffset", "50%");
    tp.setAttribute("text-anchor", "middle");
    if (dy != null) tp.setAttribute("dy", dy);
    tp.textContent = "Ever after";
    t.appendChild(tp);
    svg.appendChild(t);
    const b = t.getBBox();
    svg.remove();
    return { x: b.x, y: b.y, w: b.width, h: b.height, top: b.y, bottom: b.y + b.height };
  }

  const TOP = "M30,100 a70,70 0 1,1 140,0";
  const BOT = "M30,100 a70,70 0 0,0 140,0";
  // outer radius of each band measured from center (100,100):
  const topAlpha = arc(TOP, "t", null);
  const botAlpha = arc(BOT, "b", null);
  out.alphabetic = {
    topOuterR: 100 - topAlpha.top,      // 12 o'clock outer edge
    botOuterR: botAlpha.bottom - 100,   // 6 o'clock outer edge
    top: topAlpha, bot: botAlpha,
  };

  // try dominant-baseline:central equivalent by measuring with central set
  function arcCentral(dPath, which) {
    const svg = mk();
    const defs = document.createElementNS(NS, "defs");
    const p = document.createElementNS(NS, "path");
    p.setAttribute("id", "pc_" + which);
    p.setAttribute("d", dPath);
    defs.appendChild(p);
    svg.appendChild(defs);
    const t = document.createElementNS(NS, "text");
    styleText(t);
    t.setAttribute("dominant-baseline", "central");
    const tp = document.createElementNS(NS, "textPath");
    tp.setAttribute("href", "#pc_" + which);
    tp.setAttribute("startOffset", "50%");
    tp.setAttribute("text-anchor", "middle");
    tp.textContent = "Ever after";
    t.appendChild(tp);
    svg.appendChild(t);
    const b = t.getBBox();
    svg.remove();
    return { top: b.y, bottom: b.y + b.height };
  }
  const topC = arcCentral(TOP, "t");
  const botC = arcCentral(BOT, "b");
  out.central = { topOuterR: 100 - topC.top, botOuterR: botC.bottom - 100 };

  // FIX candidate: geometric pre-compensation, alphabetic baseline, no dy.
  const TOP_FIX = "M36,100 a64,64 0 1,1 128,0";
  const BOT_FIX = "M24,100 a76,76 0 0,0 152,0";
  const tf = arc(TOP_FIX, "tf", null);
  const bf = arc(BOT_FIX, "bf", null);
  out.fix = {
    topOuterR: 100 - tf.top,
    botOuterR: bf.bottom - 100,
    topCenterR: 100 - (tf.top + tf.h / 2),     // band-box center radius
    botCenterR: (bf.bottom - bf.h / 2) - 100,
  };

  out.FONT = FONT;
  return out;
});

console.log(JSON.stringify(result, null, 2));
await browser.close();
