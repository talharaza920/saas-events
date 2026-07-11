/** Dev-only AI wizard smoke (AI_WIZARD_PLAN 8.4b): drives the REAL UI through
 * the whole loop — admin AI tab (story-chapter run → amber grounding flag →
 * regenerate → pick the other variant → apply, then a mark run → apply → "use
 * as cover icon"), the guest cover rendering the AI mark, the platform AI
 * console, and the /create story wizard — with server-side API checks where a
 * visual can lie.
 * Requires backend :8000 (AI_TEXT_PROVIDER=fake) + frontend :3000 + a
 * scripts.dev_setup seed (which enables AI on the local default plan).
 * Usage: node scripts/smoke-ai.mjs
 */
import { mkdirSync } from "node:fs";
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const API = "http://localhost:8000";
const TOKEN = process.env.DEV_ADMIN_TOKEN || "saas-events-local-dev";
const OUT = "./.shots";
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const ok = (name, pass, detail = "") => {
  results.push({ name, pass });
  console.log(`${pass ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
};

const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 900, deviceScaleFactor: 1.5 });

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
/** True when the text is VISIBLE somewhere on the page (leaf elements only). */
const visibleHas = (text) =>
  page.evaluate(
    (t) =>
      [...document.querySelectorAll("body *")].some(
        (e) => e.children.length === 0 && e.offsetParent !== null && e.textContent.includes(t),
      ),
    text,
  );
/** Poll until the text is visible (the fake pipeline still takes real HTTP round-trips). */
async function waitFor(text, attempts = 30) {
  for (let i = 0; i < attempts; i++) {
    if (await visibleHas(text)) return true;
    await sleep(500);
  }
  return false;
}
/** Type into the (visible) MUI multiline textarea matched by placeholder. */
async function typeStory(placeholderPart, text) {
  const el = await page.$(`textarea[placeholder*="${placeholderPart}"]`);
  if (!el) return false;
  await el.click();
  await el.type(text);
  return true;
}
/** Click a variant card by its chip label ("Version 2") — the clickable Paper
 * is the chip's ancestor, so a bare text match would hit an outer container. */
const clickVariant = (label) =>
  page.evaluate((t) => {
    const chip = [...document.querySelectorAll(".MuiChip-label")].find((e) => e.textContent === t);
    const card = chip?.closest(".MuiPaper-root");
    if (card) card.click();
    return Boolean(card);
  }, label);
const api = (path) =>
  fetch(`${API}${path}`, { headers: { Authorization: `Bearer ${TOKEN}` } }).then((r) => r.json());

const STORY =
  "We're Alex and Sam. We met at a bus stop in the rain and we're getting married at Fern Hall on May 1st, 2027.";

// --- 1. Admin AI tab: story-chapter run end to end ---------------------------
await page.goto("http://localhost:3000/alex-and-sam/admin", { waitUntil: "networkidle0" });
await sleep(1500);
await clickText('button[role="tab"]', "AI");
await sleep(800);
ok("admin AI tab: panel + credits render", (await visibleHas("AI assistant")) && (await visibleHas("Credits:")));

// A leftover active run (re-run of this script) would 409 the new one.
if (await visibleHas("Discard this run")) {
  await clickText("button", "Discard this run");
  await sleep(800);
}

ok("admin AI tab: story textarea present", await typeStory("Required for a story chapter", STORY));
await clickText("button", "Draft a story chapter");
ok("story run: reaches review", await waitFor("Here's what it made"));
ok("story run: amber grounding flag shown", await visibleHas("A fact-check pass"));
await page.screenshot({ path: `${OUT}/ai-story-review.png` });

// Regenerate (first one is free), then pick the new variant. The two demo
// arcs alternate (per-process cycle), so assert the INTRO SWAPPED rather than
// pinning which one comes second.
const hadBusIntro = await visibleHas("A missed bus");
await clickText("button", "Regenerate");
ok("story run: regen produces a second variant", await waitFor("Version 2"));
await clickVariant("Version 2");
ok(
  "story run: selecting the variant swaps the proposal",
  await waitFor(hadBusIntro ? "Six years" : "A missed bus"),
);
await page.screenshot({ path: `${OUT}/ai-story-variants.png` });

await clickText("button", "Apply");
ok("story run: applied", await waitFor("Applied to your wedding"));

// Definitive check: the arc row exists server-side with AI provenance.
const arcs = await api("/api/w/alex-and-sam/admin/story-arcs");
const aiArc = arcs.find((a) => a.content?.ai_generated === true);
ok("story run: ai_generated arc persisted via the allowlisted writer", Boolean(aiArc), aiArc?.title);

// --- 2. Mark (glyph) run + "use as cover icon" -------------------------------
await clickText("button", "Design a mark");
ok("glyph run: reaches review", await waitFor("Your mark"));
await clickText("button", "Apply");
ok("glyph run: applied", await waitFor("Applied to your wedding"));
await clickText("label", "Use it as your cover icon");
await sleep(1200);
const content = await api("/api/w/alex-and-sam/admin/content");
ok(
  "glyph: icon_mode=svg + sanitised mark stored",
  content.content?.brand?.icon_mode === "svg" && Boolean(content.content?.brand?.icon_svg),
);
await page.screenshot({ path: `${OUT}/ai-glyph-applied.png` });

// The guest cover actually renders the STORED sanitised mark (Wordmark's svg
// mode) — comparing against the API's icon_svg, since the built-in cat glyph
// is also a 100×100 svg and a bare selector match would lie.
await page.goto("http://localhost:3000/i/solo-demo", { waitUntil: "networkidle0" });
await sleep(800);
const storedMark = String(content.content?.brand?.icon_svg ?? "");
ok(
  "guest cover: AI mark rendered inline",
  storedMark.length > 0 &&
    (await page.evaluate(
      (probe) =>
        [...document.querySelectorAll('svg[viewBox="0 0 100 100"]')].some((el) =>
          el.innerHTML.includes(probe),
        ),
      storedMark.slice(0, 30),
    )),
);
await page.screenshot({ path: `${OUT}/ai-cover-mark.png` });

// --- 3. Platform AI console ---------------------------------------------------
await page.goto("http://localhost:3000/platform", { waitUntil: "networkidle0" });
await sleep(1200);
await clickText('button[role="tab"]', "AI");
await sleep(1200);
ok("platform AI: breaker + usage + prompts render",
  (await visibleHas("Circuit breaker")) && (await visibleHas("Usage — last 30 days")) && (await visibleHas("Prompt registry")));
ok("platform AI: registry lists the pipeline keys", await visibleHas("draft_arc.system"));
await page.screenshot({ path: `${OUT}/ai-platform-console.png` });

// --- 4. /create with a story: wedding first, then the wizard inline ----------
await page.goto("http://localhost:3000/create", { waitUntil: "networkidle0" });
await sleep(800);
const names = `Smoke & Test ${Date.now() % 100000}`; // unique slug per run
const nameInput = await page.$("input");
await nameInput.type(names);
ok("/create: story field present", await typeStory("How you met", STORY));
await sleep(600); // let the slug availability check settle
await clickText("button", "Create & draft with AI");
ok("/create: wizard drafts after creating the wedding", await waitFor("Here's what it made"));
await page.screenshot({ path: `${OUT}/ai-create-review.png` });
await clickText("button", "Apply");
ok("/create: applied + dashboard handoff", await waitFor("Go to your dashboard"));
await page.screenshot({ path: `${OUT}/ai-create-applied.png` });

await browser.close();
const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} checks passed; shots in ${OUT}`);
process.exit(failed.length ? 1 : 0);
