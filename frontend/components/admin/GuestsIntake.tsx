"use client";

import { useState } from "react";

import Stack from "@mui/material/Stack";

import AiAssist from "@/components/ai/AiAssist";
import { type AdminMe } from "@/lib/adminApi";

import SheetImport from "./SheetImport";

// Mirrors backend storage.ALLOWED_AI_MEDIA_TYPES' sheet entries.
const SHEET_ACCEPT = ".xlsx,.csv";
const SHEET_TYPES = [
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "text/csv",
  "application/csv",
];

function isSheet(file: File): boolean {
  const name = file.name.toLowerCase();
  return SHEET_TYPES.includes(file.type) || name.endsWith(".xlsx") || name.endsWith(".csv");
}

/**
 * ONE way in for a guest list (AI_WIZARD_PLAN 8.5c) — paste it, photograph it,
 * or drop the spreadsheet — with the routing done for the couple instead of
 * asked of them:
 *
 *   a real spreadsheet ─▶ the deterministic importer (a parser; no model, no credits)
 *   anything else      ─▶ the `guests` AI run (which asks about lines it can't read)
 *
 * They shouldn't have to know which of our two code paths their list belongs to,
 * and we shouldn't charge them a credit for a table a parser can read. If the
 * sheet turns out not to be our layout, SheetImport offers the AI as the
 * fallback — a choice, made after we've tried the free path.
 */
export default function GuestsIntake({
  me,
  onChanged,
}: {
  me: AdminMe;
  /** Fired after guests are added by either route. */
  onChanged: () => void;
}) {
  const [sheet, setSheet] = useState<File | null>(null);
  // Set when the couple sends a sheet to the AI after the deterministic read
  // found nothing usable: the intake reopens with the file already attached.
  const [handOff, setHandOff] = useState<File | null>(null);

  if (sheet) {
    return (
      <SheetImport
        file={sheet}
        onDone={onChanged}
        onCancel={() => setSheet(null)}
        onFallback={(f) => {
          setSheet(null);
          setHandOff(f);
        }}
      />
    );
  }

  return (
    <Stack spacing={2}>
      <AiAssist
        me={me}
        kind="guests"
        accept={SHEET_ACCEPT}
        initialFiles={handOff ? [handOff] : undefined}
        blurb={
          "However your list exists today: a spreadsheet, a WhatsApp thread, a note, a photo of a " +
          "page. A spreadsheet is read directly — no AI, no credits. Anything else goes to the " +
          "assistant, which asks about any line it can't read rather than guessing. Who gets a +1 " +
          "comes from your own markers, and you check every row before it's added."
        }
        placeholder="Jordan Lee, Riley Park +1, Casey Nguyen + 2 kids…"
        cta="Add my guest list"
        routeFiles={(files, text) => {
          // A sheet on its own is a parser's job. A sheet mixed with a paste or a
          // voice note is part of a messier submission — that goes to the AI,
          // where it's still flattened to text in code (app/ai/sheets.py).
          // The one sheet we must NOT re-route is the one the importer just gave
          // back: they've already chosen the assistant for it.
          if (!text && files.length === 1 && isSheet(files[0]) && files[0] !== handOff) {
            setSheet(files[0]);
            return true;
          }
          return false;
        }}
        onApplied={onChanged}
      />
    </Stack>
  );
}
