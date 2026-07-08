"use client";

import { useRef, useState } from "react";

import DownloadIcon from "@mui/icons-material/Download";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";

import {
  adminApi,
  downloadTemplate,
  downloadXlsx,
  type ImportResult,
} from "@/lib/adminApi";

/**
 * Export the guest list (XLSX), grab a fillable template, and import a filled sheet.
 * Import is a two-step flow: a server **dry-run** previews creates/updates/errors per
 * invitee, then "Apply" commits. The sheet is split-row (one row per person) keyed on
 * the Id (UUID) column — a filled Id updates that guest, a blank Id adds a new one.
 * XLSX only, so the export/template can ship value dropdowns.
 */
export default function ImportPanel({ onChanged }: { onChanged: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState(false);

  function reset() {
    setFile(null);
    setPreview(null);
    setApplied(false);
    setError(null);
    if (fileRef.current) fileRef.current.value = "";
  }

  async function onPick(f: File | null) {
    setError(null);
    setApplied(false);
    setPreview(null);
    setFile(f);
    if (!f) return;
    setBusy(true);
    try {
      setPreview(await adminApi.importGuests(f, false)); // dry-run
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not read that file.");
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const res = await adminApi.importGuests(file, true);
      setPreview(res);
      setApplied(true);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed.");
    } finally {
      setBusy(false);
    }
  }

  const errorRows = (preview?.rows ?? []).filter((r) => r.action === "error");

  return (
    <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, p: 2 }}>
      <Stack direction="row" spacing={1.5} useFlexGap flexWrap="wrap" alignItems="center">
        <Typography variant="subtitle2" sx={{ mr: 1 }}>
          Export
        </Typography>
        <Button size="small" variant="outlined" startIcon={<DownloadIcon />} onClick={() => downloadXlsx()}>
          Export by person
        </Button>
        <Button size="small" variant="outlined" startIcon={<DownloadIcon />} onClick={() => downloadTemplate()}>
          Blank template
        </Button>
        <Divider orientation="vertical" flexItem />
        <Stack direction="row" spacing={0.25} alignItems="center" sx={{ mr: 1 }}>
          <Typography variant="subtitle2">Import</Typography>
          <Tooltip
            arrow
            title={
              <Box sx={{ p: 0.5 }}>
                <Typography variant="caption" sx={{ fontWeight: 600, display: "block", mb: 0.5 }}>
                  How to import
                </Typography>
                <Typography variant="caption" component="div" sx={{ lineHeight: 1.5 }}>
                  1. <b>Download</b> either <b>Export by person</b> (your live guest data) or a{" "}
                  <b>Blank template</b>.
                  <br />
                  2. <b>Fill it in Excel</b> — keep the same columns and layout (one row per person).
                  <br />
                  3. <b>Keep each family together</b> — a Primary row, then that party&apos;s{" "}
                  <i>Guest</i>/<i>Child</i> rows beneath it. Companion rows attach to the Primary that
                  shares their <b>Id</b> (the export fills the Id on every row), so you can reorder whole
                  families freely — just don&apos;t split a companion away from its group.
                  <br />
                  4. <b>Choose file</b> here to import the <i>same format</i> back. You&apos;ll see a
                  preview of new/updated rows before anything is saved.
                </Typography>
              </Box>
            }
          >
            <HelpOutlineIcon fontSize="small" sx={{ color: "text.secondary", cursor: "help" }} />
          </Tooltip>
        </Stack>
        <Button
          size="small"
          variant="contained"
          startIcon={<UploadFileIcon />}
          onClick={() => fileRef.current?.click()}
          disabled={busy}
        >
          Choose file…
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept=".xlsx"
          hidden
          onChange={(e) => onPick(e.target.files?.[0] ?? null)}
        />
        {file && (
          <Typography variant="caption" color="text.secondary">
            {file.name}
          </Typography>
        )}
      </Stack>

      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
        <b>One row per person, grouped by party</b> — each invite&apos;s <i>Primary</i> row, then their{" "}
        <i>Guest</i>/<i>Child</i> rows beneath it. The <b>Id</b> (on every row of a party) is the invite&apos;s
        key: it ties companions to their Primary and is how an edited row updates the right invite — keep
        it to update an existing guest, leave it blank to add a new one (the Guest/Child rows aren&apos;t
        separate guests, so they share the Primary&apos;s Id). Edit a person&apos;s dietary/age on their
        own row, then re-import to bulk-update. <b>Greeting</b> is <b>required</b> on each
        Primary row — it&apos;s the invite&apos;s &quot;Dear …&quot; line and label (e.g. &quot;John &amp;
        Jane&quot;); the Name is optional. The <i>Guest</i>/<i>Child</i> <b>Name</b> rows pre-fill that
        invite&apos;s party, so the guest&apos;s RSVP opens with the +1/kids&apos; names ready to confirm
        (even before they reply). Set <b>Tier</b> (solo / plus_one / plus_family) to control their invite,
        and{" "}
        <b>Attending</b> = yes to import their RSVP + answers (the row&apos;s party replaces the stored one).{" "}
        <b>Expected</b> is your private pre-RSVP headcount estimate (0–50) — admin-only, never shown to the
        guest. <b>Actual</b> is the live RSVP head count — read-only, ignored on import.
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mt: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {preview && (
        <Box sx={{ mt: 2 }}>
          <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {applied ? "Imported:" : "Preview:"}
            </Typography>
            <Chip size="small" color="success" label={`${preview.created} new`} />
            <Chip size="small" color="info" label={`${preview.updated} updated`} />
            {preview.errors > 0 && <Chip size="small" color="error" label={`${preview.errors} errors`} />}
            <Typography variant="caption" color="text.secondary">
              {preview.created + preview.updated} invitee
              {preview.created + preview.updated === 1 ? "" : "s"} ·{" "}
              {preview.people_created + preview.people_updated} guest
              {preview.people_created + preview.people_updated === 1 ? "" : "s"} (incl. companions)
            </Typography>
            {!applied && preview.errors === 0 && preview.created + preview.updated === 0 && (
              <Typography variant="caption" color="text.secondary">
                Nothing to import.
              </Typography>
            )}
          </Stack>

          {errorRows.length > 0 && (
            <Table size="small" sx={{ mt: 1 }}>
              <TableHead>
                <TableRow>
                  <TableCell>Row</TableCell>
                  <TableCell>Invitee</TableCell>
                  <TableCell>Problem</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {errorRows.map((r, i) => (
                  <TableRow key={i}>
                    <TableCell>{r.row}</TableCell>
                    <TableCell>{r.invitee}</TableCell>
                    <TableCell>{r.detail}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {!applied && (
            <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
              <Button
                variant="contained"
                onClick={apply}
                disabled={busy || preview.created + preview.updated === 0}
              >
                {busy ? "Applying…" : `Apply (${preview.created + preview.updated})`}
              </Button>
              <Button onClick={reset} disabled={busy}>
                Cancel
              </Button>
            </Stack>
          )}
          {applied && (
            <Box sx={{ mt: 1 }}>
              <Button onClick={reset}>Done</Button>
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
}
