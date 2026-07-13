/** Dev-only AI smoke (AI_WIZARD_PLAN 8.4b, re-pointed at the 8.5a funnel):
 * drives the REAL UI through every AI entry point where it now lives — Details
 * tab (`details` run → apply → venue persisted), Story tab (story run → amber
 * grounding flag → regenerate → pick the other variant → apply), AI tab (mark →
 * apply → "use as cover icon"), Guests tab (pasted list → deterministic tiers),
 * the guest cover rendering the AI mark, the platform AI console, and the
 * /create → /setup handoff — with server-side API checks where a visual can lie.
 * Requires backend :8000 started with AI_LIVE_CALLS=false + frontend :3000 + a
 * scripts.dev_setup seed (which enables AI on the local default plan).
 * AI_LIVE_CALLS=false is the ONE switch that keeps this free: it serves the
 * offline fake text model AND holds back Places/Nano Banana, whose real keys
 * live in backend/.env (see LEARNINGS — this smoke used to spend money).
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
/** page.evaluate, but a navigation mid-call is "not there yet", not a crash —
 * these run inside polling loops that straddle client-side route changes
 * ("Finish" → /admin), which destroy the execution context under the poll. */
const evalSafe = async (fn, arg) => {
  try {
    return await page.evaluate(fn, arg);
  } catch (e) {
    if (String(e.message).includes("Execution context was destroyed")) return false;
    throw e;
  }
};
/** True when the text is VISIBLE somewhere on the page (leaf elements only). */
const visibleHas = (text) =>
  evalSafe(
    (t) =>
      [...document.querySelectorAll("body *")].some(
        (e) => e.children.length === 0 && e.offsetParent !== null && e.textContent.includes(t),
      ),
    text,
  );
/** Rendered page text. Use where the string is split across inline elements
 * (e.g. "<strong>Venue:</strong> Fern Hall"), which visibleHas's leaf-only
 * scan can't see. */
const bodyHas = (text) => evalSafe((t) => document.body.innerText.includes(t), text);
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
/** Click inside ONE card, found by its heading. The platform console has several
 * cards each with a "Save" button, and a bare text match hits the first on the
 * page (which silently saved the wrong card until this existed). */
const clickInCard = (heading, sel, text) =>
  page.evaluate(
    (h, s, t) => {
      const card = [...document.querySelectorAll(".MuiPaper-root")].find((p) =>
        [...p.querySelectorAll("h6, .MuiTypography-subtitle1")].some(
          (el) => el.textContent.trim() === h,
        ),
      );
      const el = card && [...card.querySelectorAll(s)].find((e) => e.textContent.includes(t));
      if (el) el.click();
      return Boolean(el);
    },
    heading,
    sel,
    text,
  );
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

/** Open a tab on the wedding dashboard from a clean load. */
async function openTab(label) {
  await page.goto("http://localhost:3000/alex-and-sam/admin", { waitUntil: "networkidle0" });
  await sleep(1500);
  await clickText('button[role="tab"]', label);
  await sleep(900);
}

const STORY =
  "We're Alex and Sam. We met at a bus stop in the rain and we're getting married at Fern Hall on May 1st, 2027.";

// --- 1. Details tab: the `details` run (8.5a's demoted wizard) ----------------
await openTab("Details");
ok("details tab: AI entry point present", await visibleHas("Key details with AI"));

// A leftover active run (re-run of this script) would 409 the new one.
if (await visibleHas("Discard this run")) {
  await clickText("button", "Discard this run");
  await sleep(800);
}

ok("details run: textarea present", await typeStory("Fern Hall on May 1st", STORY));
await clickText("button", "Fill in my details");
ok("details run: reaches review", await waitFor("Here's what it made"));
ok("details run: proposes the extracted venue", await bodyHas("Fern Hall"));
await page.screenshot({ path: `${OUT}/ai-details-review.png` });
await clickText("button", "Apply");
ok("details run: applied", await waitFor("Applied to your wedding"));

const content = await api("/api/w/alex-and-sam/admin/content");
ok(
  "details run: venue persisted through the allowlisted writer",
  content.event_details?.venue === "Fern Hall",
  content.event_details?.venue,
);

// --- 2. Story tab: story-chapter run end to end -------------------------------
await openTab("Story");
ok("story tab: AI entry point present", await visibleHas("Story chapter with AI"));
ok("story run: textarea present", await typeStory("bus stop in the rain", STORY));
// The seeded template already has an arc, so the CTA is the "another" variant;
// on an empty wedding it reads "Draft my story".
if (!(await clickText("button", "Draft another chapter"))) {
  await clickText("button", "Draft my story");
}
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

// --- 3. AI tab: mark (glyph) run + "use as cover icon" ------------------------
await openTab("AI");
ok("AI tab: panel + credits render", (await visibleHas("AI assistant")) && (await visibleHas("Credits:")));
await clickText("button", "Design a mark");
ok("glyph run: reaches review", await waitFor("Your mark"));
await clickText("button", "Apply");
ok("glyph run: applied", await waitFor("Applied to your wedding"));
await clickText("label", "Use it as your cover icon");
await sleep(1200);
const withMark = await api("/api/w/alex-and-sam/admin/content");
ok(
  "glyph: icon_mode=svg + sanitised mark stored",
  withMark.content?.brand?.icon_mode === "svg" && Boolean(withMark.content?.brand?.icon_svg),
);
await page.screenshot({ path: `${OUT}/ai-glyph-applied.png` });

// The guest cover actually renders the STORED sanitised mark (Wordmark's svg
// mode) — comparing against the API's icon_svg, since the built-in cat glyph
// is also a 100×100 svg and a bare selector match would lie.
await page.goto("http://localhost:3000/i/solo-demo", { waitUntil: "networkidle0" });
await sleep(800);
const storedMark = String(withMark.content?.brand?.icon_svg ?? "");
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

// --- 4. Guests tab: raw markers in, deterministic tiers out -------------------
await openTab("Guests");
ok("guests tab: AI entry point present", await visibleHas("Guest list with AI"));
// The label button wraps a hidden <input type=file>, so it isn't a leaf —
// match the button + its input directly rather than via visibleHas.
ok(
  "guests run: attach-files control present",
  await page.evaluate(() =>
    [...document.querySelectorAll("button, label")].some(
      (b) => b.textContent.includes("Attach files") && b.querySelector('input[type="file"]'),
    ),
  ),
);
ok(
  "guests run: textarea present",
  await typeStory("Jordan Lee, Riley Park", "Jordan, Riley +1, Casey and family"),
);
await clickText("button", "Read my guest list");
ok("guests run: reaches review", await waitFor("Here's what it made"));
ok(
  "guests run: names + owner-facing tier chips shown",
  (await visibleHas("Riley Park")) && (await visibleHas("Family")),
);
await page.screenshot({ path: `${OUT}/ai-guests-review.png` });
await clickText("button", "Apply");
ok("guests run: applied", await waitFor("Applied to your wedding"));
const guestRows = await api("/api/w/alex-and-sam/admin/guests");
const riley = guestRows.find((g) => g.name === "Riley Park");
const casey = guestRows.find((g) => g.name === "Casey Nguyen");
ok(
  "guests run: rows persisted with tiers from the +1/kid markers (never the model)",
  riley?.invite_tier === "plus_one" && casey?.invite_tier === "plus_family",
);

// --- 5. Platform AI console ---------------------------------------------------
await page.goto("http://localhost:3000/platform", { waitUntil: "networkidle0" });
await sleep(1200);
await clickText('button[role="tab"]', "AI");
await sleep(1200);
ok("platform AI: breaker + usage + prompts render",
  (await visibleHas("Circuit breaker")) && (await visibleHas("Usage — last 30 days")) && (await visibleHas("Prompt registry")));
ok("platform AI: registry lists the pipeline keys", await visibleHas("draft_arc.system"));

// The text-model card. The backend runs with AI_LIVE_CALLS=false here, so the
// console must SAY the selection isn't being called rather than name a model
// it isn't using.
ok("platform AI: text-model card renders", await visibleHas("Text model"));
ok(
  "platform AI: says the offline model is answering (live calls off)",
  await bodyHas("offline demo model is answering"),
);

// Change the model through the UI (MUI select → listbox option), then verify
// server-side. This is also the regression guard for the whole-blob PUT: the
// breaker's ceiling must survive a model save.
// Give the breaker a NON-default ceiling first, so the whole-blob check below
// can actually fail: if the model save wiped the breaker, this reverts to 25.
await page.evaluate(() => {
  const card = [...document.querySelectorAll(".MuiPaper-root")].find((p) =>
    [...p.querySelectorAll("h6, .MuiTypography-subtitle1")].some(
      (el) => el.textContent.trim() === "Circuit breaker",
    ),
  );
  const input = card.querySelector('input[type="text"], input:not([type])');
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  setter.call(input, "7"); // React tracks value on the node — bypass its cache
  input.dispatchEvent(new Event("input", { bubbles: true }));
});
await sleep(300);
await clickInCard("Circuit breaker", "button", "Save");
await sleep(1200);

// Now change the provider through the Text model card. A MUI Select opens on
// MOUSEDOWN, so a synthetic el.click() does nothing — drive it with a real
// mouse click (elementHandle.click dispatches the full sequence).
const providerSelect = await page.evaluateHandle(() => {
  const card = [...document.querySelectorAll(".MuiPaper-root")].find((p) =>
    [...p.querySelectorAll("h6, .MuiTypography-subtitle1")].some(
      (el) => el.textContent.trim() === "Text model",
    ),
  );
  return card?.querySelector('div[role="combobox"]'); // Provider = the first
});
await providerSelect.asElement()?.click();
await sleep(600);
const option = await page.evaluateHandle(() =>
  [...document.querySelectorAll('li[role="option"]')].find(
    (o) => o.textContent.trim() === "anthropic",
  ),
);
await option.asElement()?.click();
await sleep(400);
await clickInCard("Text model", "button", "Save");
await sleep(1500);
const aiCfg = await api("/api/platform/settings/ai");
ok(
  "platform AI: model choice saved + resolved to the provider's default",
  aiCfg.text_provider === "anthropic" && aiCfg.effective_model === "claude-opus-4-8",
  `${aiCfg.text_provider}/${aiCfg.effective_model}`,
);
ok(
  "platform AI: saving the model did not wipe the circuit breaker",
  aiCfg.daily_cost_ceiling_usd === 7 && aiCfg.kill_switch === false,
  `ceiling=${aiCfg.daily_cost_ceiling_usd} kill=${aiCfg.kill_switch}`,
);
await page.screenshot({ path: `${OUT}/ai-platform-console.png` });

// --- 6. /create → /setup: the wedding exists immediately, setup is optional ---
await page.goto("http://localhost:3000/create", { waitUntil: "networkidle0" });
await sleep(800);
const names = `Smoke & Test ${Date.now() % 100000}`; // unique slug per run
const nameInput = await page.$("input");
await nameInput.type(names);
ok("/create: slimmed to names + address (no story field)", !(await page.$('textarea')));
await sleep(700); // let the slug availability check settle
await clickText("button", "Create wedding");
ok("/create: hands off to the setup flow", await waitFor("Key details"));
ok("setup: all three steps offered", (await visibleHas("Your story")) && (await visibleHas("Guest list")));
ok("setup: step 1 offers the details assistant", await visibleHas("Key details with AI"));
await page.screenshot({ path: `${OUT}/ai-setup-step1.png` });

await clickText("button", "Skip this step");
ok("setup: step 2 offers the story assistant", await waitFor("Story chapter with AI"));
await clickText("button", "Skip this step");
ok("setup: step 3 offers the guests assistant", await waitFor("Guest list with AI"));
await page.screenshot({ path: `${OUT}/ai-setup-step3.png` });
await clickText("button", "Finish");
ok("setup: finishing lands on the dashboard", await waitFor("Overview"));
// Dismissed on finish, so the checklist card must be gone even though the
// wedding is empty (nothing was applied — every step was skipped).
ok("setup: checklist dismissed after finishing", !(await visibleHas("Finish setting up your wedding")));
await page.screenshot({ path: `${OUT}/ai-setup-done.png` });

await browser.close();
const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} checks passed; shots in ${OUT}`);
process.exit(failed.length ? 1 : 0);
