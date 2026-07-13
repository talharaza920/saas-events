"""Spreadsheets are not an AI problem (AI_WIZARD_PLAN Phase 8.5c).

A guest list that is already a table is already structured: reading it needs a
parser, not a model. So a real spreadsheet takes the deterministic path — the
existing `/import` endpoint, which has understood the split-row template since
long before the wizard existed, and which costs nothing.

This module is the OTHER case: a sheet that isn't our template ("Guest | Side |
Notes", the one a friend made). The couple shouldn't have to reshape it by hand,
so it may be submitted to the `guests` job — and even then the sheet itself
never reaches a provider. It is flattened to text HERE, in code, and only the
messy lines that come out of it go to the model. No cell of it is ever sent to
Gemini as a file, and the flattening costs nothing.

Bounds are the point: a workbook can decompress far larger than it uploads, and
everything below feeds a prompt.
"""
from __future__ import annotations

import csv
import io

from app.storage import UploadError

# Sheet-shaped uploads (mime → canonical extension). `.xls` (the legacy binary
# format) is deliberately absent: openpyxl cannot read it, and a wrong answer
# here is a confusing error rather than a missing feature.
SHEET_MIMES: dict[str, str] = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/csv": "csv",
    "application/csv": "csv",
}

# What one sheet may contribute. A guest list past this isn't a guest list a
# model should be reading — it's an import.
MAX_SHEET_ROWS = 1_000
MAX_SHEET_COLS = 15
MAX_CELL_CHARS = 120


def is_sheet_mime(mime: str | None) -> bool:
    return (mime or "").lower() in SHEET_MIMES


def _cell(value) -> str:
    if value is None:
        return ""
    return str(value).strip().replace("\n", " ")[:MAX_CELL_CHARS]


def sheet_to_text(data: bytes, mime: str | None) -> str:
    """Flatten a CSV/XLSX into pipe-joined lines ("Riley Park | bride | +1"),
    header row included so the model can see what the columns mean. Raises
    UploadError on anything unreadable — the caller turns that into a clean
    "we couldn't read that file", never a stack trace."""
    rows: list[list[str]] = []
    if (mime or "").lower() in ("text/csv", "application/csv"):
        try:
            text = data.decode("utf-8-sig", errors="replace")
        except Exception as exc:  # pragma: no cover - decode with errors= won't raise
            raise UploadError(f"could not read that CSV ({exc})") from exc
        for row in csv.reader(io.StringIO(text)):
            rows.append([_cell(c) for c in row[:MAX_SHEET_COLS]])
            if len(rows) >= MAX_SHEET_ROWS:
                break
    else:
        try:
            import openpyxl

            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            ws = wb.active
            for raw in ws.iter_rows(values_only=True):
                rows.append([_cell(c) for c in raw[:MAX_SHEET_COLS]])
                if len(rows) >= MAX_SHEET_ROWS:
                    break
            wb.close()
        except Exception as exc:
            raise UploadError(f"could not read that spreadsheet ({exc})") from exc

    lines = [" | ".join(c for c in row).strip(" |") for row in rows]
    return "\n".join(line for line in lines if line)
