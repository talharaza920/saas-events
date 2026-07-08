/** Dev-only: screenshot (1) the RSVP nav button on an intermediate step ("Next"),
 * (2) the final step ("Send my RSVP"), and (3) the admin Buttons editor with its
 * new descriptive labels. Usage: node scripts/rsvp-buttons-shots.mjs */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const SLUG = process.argv[2] || "family-demo";
const OUT = "./.shots";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"] });

const clickText = (page, sel, text) =>
  page.evaluate(
    (s, t) => {
      const el = [...document.querySelectorAll(s)].find((e) => e.textContent.trim().includes(t));
      if (el) el.click();
      return !!el;
    },
    sel,
    text,
  );
const navLabel = (page) =>
  page.evaluate(() => {
    const card = document.getElementById("rsvp");
    const btns = [...(card?.querySelectorAll("button.MuiButton-contained") ?? [])];
    return btns.map((b) => b.textContent.trim()).join(" | ");
  });

// ---- 1 & 2: the guest RSVP flow ------------------------------------------
{
  const page = await browser.newPage();
  await page.setViewport({ width: 760, height: 1000, deviceScaleFactor: 2 });
  await page.goto(`http://localhost:3000/i/${SLUG}`, { waitUntil: "networkidle0" });
  await page.evaluateHandle("document.fonts.ready");
  await page.evaluate(() => document.getElementById("rsvp")?.scrollIntoView());
  await sleep(300);
  await clickText(page, '[role="button"]', "Joyfully");
  await sleep(400);

  const heading = () => page.evaluate(() => document.querySelector("#rsvp h3")?.textContent?.trim());
  let nextShot = false;
  // Advance to the last step (review = "Look good?"), filling required fields.
  for (let i = 0; i < 8; i++) {
    const h = await heading();
    console.log(`step ${i}: heading="${h}" nav="${await navLabel(page)}"`);
    if (h === "Look good?") break;
    // Contacts step needs an email or phone to proceed.
    if (h === "How can we reach you?") {
      const typed = await page.evaluate(() => {
        const inp = document.querySelector('#rsvp input[type="email"]');
        if (!inp) return false;
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
        setter.call(inp, "demo@example.com");
        inp.dispatchEvent(new Event("input", { bubbles: true }));
        return true;
      });
      console.log(`  filled email: ${typed}`);
      await sleep(250);
    }
    // Capture the "Next" example at the guests step (Back + Next both visible).
    if (!nextShot && h === "Who's coming?") {
      await (await page.$("#rsvp")).screenshot({ path: `${OUT}/rsvp-next-step.png` });
      console.log(`shot -> ${OUT}/rsvp-next-step.png`);
      nextShot = true;
    }
    await clickText(page, "button.MuiButton-contained", "Next");
    await sleep(550);
  }
  await sleep(300);
  console.log("final nav button:", await navLabel(page));
  await (await page.$("#rsvp")).screenshot({ path: `${OUT}/rsvp-send-step.png` });
  console.log(`shot -> ${OUT}/rsvp-send-step.png`);
  await page.close();
}

// ---- 3: the admin Buttons editor -----------------------------------------
{
  const page = await browser.newPage();
  await page.setViewport({ width: 1100, height: 1200, deviceScaleFactor: 2 });
  await page.goto("http://localhost:3000/admin", { waitUntil: "networkidle0" });
  await page.evaluateHandle("document.fonts.ready");
  await sleep(1000);
  // Open the Details/Content tab if the dashboard is tabbed.
  await clickText(page, '[role="tab"], button, a', "Details");
  await sleep(700);
  console.log("accordions:", await page.evaluate(() =>
    [...document.querySelectorAll(".MuiAccordionSummary-root")].map((e) => e.textContent.trim().slice(0, 30))));
  // Expand the "RSVP steps & buttons" accordion.
  const expanded = await clickText(page, ".MuiAccordionSummary-root", "RSVP steps & buttons");
  console.log("expanded accordion:", expanded);
  await sleep(900);
  // Centre the "Continue button" field (first of the buttons editor) in the viewport.
  const found = await page.evaluate(() => {
    const lab = [...document.querySelectorAll("label")].find((e) => e.textContent.trim().startsWith("Continue button"));
    if (!lab) return false;
    lab.scrollIntoView({ block: "center" });
    window.scrollBy(0, -160); // show the "Buttons" subheading above the fields
    return true;
  });
  console.log("found Continue button field:", found);
  await sleep(500);
  await page.screenshot({ path: `${OUT}/admin-buttons-editor.png` });
  console.log(`shot -> ${OUT}/admin-buttons-editor.png`);
  await page.close();
}

await browser.close();
