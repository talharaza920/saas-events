"use client";

import { useCallback, useEffect, useState } from "react";

import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";

import { adminApi, type ImportResult } from "@/lib/adminApi";

/**
 * The deterministic guest-sheet import (AI_WIZARD_PLAN 8.5c routes a real
 * spreadsheet here). A table is already structured, so reading it is a parser's
 * job: no model, no credits, and the same server-side dry-run → preview → commit
 * the Import panel has always used. The `Id` column is the upsert key, so an
 * exported-and-edited sheet UPDATES its guests instead of duplicating them.
 *
 * When the sheet isn't our layout, the honest answer is not an error message —
 * it's `onFallback`: hand the same file to the assistant, which reads whatever
 * shape it happens to be in (that path does cost a credit, so it's a choice, not
 * a default).
 */
export default function SheetImport({
  file,
  onDone,
  onCancel,
  onFallback,
}: {
  file: File;
  /** Fired after a committed import so the guest list refreshes. */
  onDone: () => void;
  onCancel: () => void;
  /** "Let the assistant read it instead" — only offered when the sheet doesn't parse. */
  onFallback?: (file: File) => void;
}) {
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState(false);

  const dryRun = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setPreview(await adminApi.importGuests(file, false));
    } catch (e) {
      setPreview(null);
      setError(e instanceof Error ? e.message : "Could not read that file.");
    } finally {
      setBusy(false);
    }
  }, [file]);

  useEffect(() => {
    // Fetch-on-mount: setState only happens after dryRun()'s first await.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    dryRun();
  }, [dryRun]);

  const commit = async () => {
    setBusy(true);
    setError(null);
    try {
      setPreview(await adminApi.importGuests(file, true));
      setApplied(true);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed.");
    } finally {
      setBusy(false);
    }
  };

  const invitees = (preview?.created ?? 0) + (preview?.updated ?? 0);
  const errorRows = (preview?.rows ?? []).filter((r) => r.action === "error");
  // Nothing we could use: not our column layout, or every row is an error. The
  // sheet isn't wrong — it just isn't ours.
  const unreadable = !busy && (error !== null || (invitees === 0 && !applied));

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Stack spacing={2}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
          <Typography variant="subtitle1" sx={{ flexGrow: 1 }}>
            {file.name}
          </Typography>
          <Chip size="small" variant="outlined" label="Read directly — no AI credits" />
        </Stack>

        {busy && !preview && (
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <CircularProgress size={18} />
            <Typography variant="body2" color="text.secondary">
              Reading your spreadsheet…
            </Typography>
          </Stack>
        )}

        {error && <Alert severity="error">{error}</Alert>}

        {preview && (
          <Stack spacing={1}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {applied ? "Imported:" : "Preview:"}
              </Typography>
              <Chip size="small" color="success" label={`${preview.created} new`} />
              <Chip size="small" color="info" label={`${preview.updated} updated`} />
              {preview.errors > 0 && (
                <Chip size="small" color="error" label={`${preview.errors} errors`} />
              )}
              <Typography variant="caption" color="text.secondary">
                {preview.people_created + preview.people_updated} guest
                {preview.people_created + preview.people_updated === 1 ? "" : "s"} (incl.
                companions)
              </Typography>
            </Stack>

            {errorRows.length > 0 && (
              <Box sx={{ overflowX: "auto" }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Row</TableCell>
                      <TableCell>Invitee</TableCell>
                      <TableCell>Problem</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {errorRows.slice(0, 20).map((r, i) => (
                      <TableRow key={i}>
                        <TableCell>{r.row}</TableCell>
                        <TableCell>{r.invitee}</TableCell>
                        <TableCell>{r.detail}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            )}
          </Stack>
        )}

        {unreadable && (
          <Alert
            severity="info"
            action={
              onFallback && (
                <Button
                  size="small"
                  startIcon={<AutoAwesomeIcon />}
                  onClick={() => onFallback(file)}
                >
                  Let the assistant read it
                </Button>
              )
            }
          >
            Nothing here matches our sheet layout (a <b>Greeting</b> column at least, one row per
            person). Either fix the columns and try again, or hand the same file to the assistant —
            it reads whatever shape your list is in, and costs 1 credit.
          </Alert>
        )}

        <Stack direction="row" spacing={1.5}>
          {!applied && invitees > 0 && (
            <Button variant="contained" disabled={busy} onClick={commit}>
              {busy ? "Importing…" : `Import ${invitees}`}
            </Button>
          )}
          <Button color="inherit" disabled={busy} onClick={onCancel}>
            {applied ? "Done" : "Cancel"}
          </Button>
        </Stack>
      </Stack>
    </Paper>
  );
}
