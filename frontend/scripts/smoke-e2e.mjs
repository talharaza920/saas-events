/** Dev-only full smoke test: walks each demo tier's invite, completes a full
 * RSVP as the family guest (verified via the API, not just the UI), checks the
 * tier-invisibility rule, and shots the admin dashboard.
 * Requires backend :8000 + frontend :3000 + scripts.dev_setup seed.
 * Usage: node scripts/smoke-e2e.mjs
 *
 * NOTE: never assert on document.body.textContent — Next serializes the whole
 * wedding content into a <script> payload, so every copy string "exists" on
 * every page. All checks here use VISIBLE leaf elements only.
 */
import { mkdirSync } from "node:fs";
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const API = "http://localhost:8000";
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
/** Same, scoped to the RSVP card. */
const rsvpShows = (text) =>
  page.evaluate((t) => {
    const card = document.getElementById("rsvp");
    if (!card) return false;
    return [...card.querySelectorAll("*")].some(
      (e) => e.children.length === 0 && e.offsetParent !== null && e.textContent.includes(t),
    );
  }, text);
const fillEmail = async () => {
  const em = await page.$('input[type="email"], input[name="email"]');
  if (em) {
    await em.click({ clickCount: 3 });
    await em.type("smoke-test@example.com");
  }
  return !!em;
};
/** Advance with Next until a step title is visible (or attempts run out). */
async function advanceTo(title, attempts = 6) {
  for (let i = 0; i < attempts; i++) {
    if (await visibleHas(title)) return true;
    await fillEmail();
    await clickText("button", "Next");
    await sleep(450);
  }
  return visibleHas(title);
}

async function openInvite(slug) {
  await page.goto(`http://localhost:3000/i/${slug}`, { waitUntil: "networkidle0" });
  await page.evaluateHandle("document.fonts.ready");
  await sleep(300);
}

// --- 1. Covers render for all three tiers -----------------------------------
for (const slug of ["solo-demo", "plusone-demo", "family-demo"]) {
  await openInvite(slug);
  ok(`${slug}: invite renders`, await visibleHas("Alex & Sam"));
  await page.screenshot({ path: `${OUT}/${slug}-cover.png` });
}

// --- 2. Tier invisibility: solo guest must never SEE +1/kids fields ---------
await openInvite("solo-demo");
await page.evaluate(() => document.getElementById("rsvp")?.scrollIntoView());
await sleep(400);
await clickText('[role="button"]', "Joyfully accepts");
await sleep(400);
let soloLeaked = false;
let soloReachedReview = false;
for (let i = 0; i < 6; i++) {
  for (const t of ["bringing a +1", "Bringing other guests", "Bringing little ones"]) {
    if (await rsvpShows(t)) soloLeaked = true;
  }
  if (await visibleHas("Look good?")) {
    soloReachedReview = true;
    break;
  }
  await fillEmail();
  await clickText("button", "Next");
  await sleep(450);
}
ok("solo: no visible +1/kids UI anywhere in the flow", !soloLeaked);
ok("solo: reached the review step", soloReachedReview);
await page.screenshot({ path: `${OUT}/solo-demo-rsvp.png` });

// --- 3. Full RSVP as the family guest, verified via the API ------------------
await openInvite("family-demo");
await page.evaluate(() => document.getElementById("rsvp")?.scrollIntoView());
await sleep(400);
await clickText('[role="button"]', "Joyfully accepts");
await sleep(400);
await clickText("button", "Next");
await sleep(450);

ok("family: contacts step shown", (await visibleHas("How can we reach you?")) && (await fillEmail()));
await clickText("button", "Next");
await sleep(450);

ok("family: party step shown", await visibleHas("Who's coming?"));
const sawParty =
  (await rsvpShows("Bringing other guests")) || (await rsvpShows("Bringing little ones"));
ok("family: party (adults/kids) controls visible", sawParty);
await page.screenshot({ path: `${OUT}/family-demo-party-step.png` });

// The seeded party includes a child whose required Age is empty. Number
// questions render as digit-filtered TEXT inputs (AnswerField), so just fill
// every visible empty input on this step (names are already prefilled).
for (const inp of await page.$$("#rsvp input")) {
  const empty = await inp.evaluate((e) => !e.value && e.offsetParent !== null);
  if (empty) {
    await inp.click();
    await inp.type("8");
  }
}
ok("family: reached review", await advanceTo("Look good?"));
await page.screenshot({ path: `${OUT}/family-demo-review.png` });
await clickText("button", "Send my RSVP");
await sleep(1500);
ok("family: confirmation visible after send", await visibleHas("You're on the list"));
await page.screenshot({ path: `${OUT}/family-demo-confirmed.png` });

// Definitive check: the RSVP exists server-side.
const persisted = await fetch(`${API}/api/i/family-demo`).then((r) => r.json());
ok(
  "family: RSVP persisted in the backend",
  persisted.rsvp?.attending === true,
  JSON.stringify(persisted.rsvp)?.slice(0, 80),
);

// --- 4. Landing page (no link) ----------------------------------------------
await page.goto("http://localhost:3000/", { waitUntil: "networkidle0" });
await sleep(300);
ok("landing: renders without a guest link", await visibleHas("Alex & Sam"));
await page.screenshot({ path: `${OUT}/landing.png` });

// --- 5. Post-login dashboard (dev-token auth; platform era) ------------------
await page.goto("http://localhost:3000/dashboard", { waitUntil: "networkidle0" });
await sleep(1500);
await page.screenshot({ path: `${OUT}/dashboard.png` });
ok("dashboard: lists the seeded wedding", await visibleHas("Alex & Sam"));
ok("dashboard: shows the owner role chip", await visibleHas("owner"));

// --- 6. Wedding-scoped admin dashboard ----------------------------------------
await page.goto("http://localhost:3000/alex-and-sam/admin", { waitUntil: "networkidle0" });
await sleep(1800);
await page.screenshot({ path: `${OUT}/admin-overview.png` });
ok("admin: wedding dashboard loads via dev token", await visibleHas("Alex & Sam"));
ok("admin: shows the new RSVP", await visibleHas("guests coming"));
ok("admin: lifecycle strip shows published state", await visibleHas("Published (guest links live)"));
ok("admin: Team tab present", await visibleHas("Team ("));

// --- 7. Platform console --------------------------------------------------------
await page.goto("http://localhost:3000/platform", { waitUntil: "networkidle0" });
await sleep(1500);
await page.screenshot({ path: `${OUT}/platform-console.png` });
ok("platform: console loads for the dev platform admin", await visibleHas("Platform console"));
ok("platform: weddings table lists the tenant", await visibleHas("/alex-and-sam"));

await browser.close();
const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} checks passed; shots in ${OUT}`);
process.exit(failed.length ? 1 : 0);
