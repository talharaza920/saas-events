/**
 * One-off: optimize the proposal-comic panels from the Claude Design export into
 * web-sized assets, keyed by STORY BULLET NUMBER. The originals are 8–14 MB PNGs;
 * we never commit those. Output lands in public/invite/story/0N.png (beats 01–06)
 * and public/invite/wordmark.png (panel 00).
 *
 * To re-run after the design source moves, set SRC below. To change the picture
 * for a bullet later, just drop a new file at public/invite/story/0N.png (or point
 * the beat's `image` in seed_data.py at any URL, incl. Supabase Storage).
 *
 *   node scripts/optimize-invite-images.mjs
 */
import { mkdir } from "node:fs/promises";
import path from "node:path";

import sharp from "sharp";

const SRC = process.argv[2] ?? "./assets-src"; // pass the source folder as the first argument
const OUT = path.resolve(import.meta.dirname, "../public/invite");
const STORY_OUT = path.join(OUT, "story");

// source panel -> output path. 00 is the wordmark; 01–06 are the story beats.
const JOBS = [
  { src: "panel-00-wordmark.png", out: path.join(OUT, "wordmark.png"), width: 600 },
  ...Array.from({ length: 6 }, (_, i) => {
    const n = String(i + 1).padStart(2, "0");
    return { src: `panel-0${i + 1}.png`, out: path.join(STORY_OUT, `${n}.png`), width: 1600 };
  }),
];

await mkdir(STORY_OUT, { recursive: true });

for (const { src, out, width } of JOBS) {
  const info = await sharp(path.join(SRC, src))
    .resize({ width, withoutEnlargement: true })
    .png({ quality: 80, compressionLevel: 9, palette: true })
    .toFile(out);
  console.log(`${src} -> ${path.relative(OUT, out)}  ${(info.size / 1024).toFixed(0)} KB  ${info.width}x${info.height}`);
}
console.log("done");
