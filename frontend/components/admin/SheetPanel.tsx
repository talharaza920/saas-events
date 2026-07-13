"use client";

import DownloadIcon from "@mui/icons-material/Download";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import { downloadTemplate, downloadXlsx } from "@/lib/adminApi";

/**
 * The spreadsheet round-trip: export the live list (or a blank template), edit it
 * in Excel, and bring it back through the intake above — the `Id` column is the
 * upsert key, so an edited row updates that guest rather than duplicating them.
 *
 * The import half of this panel moved into GuestsIntake (8.5c): a guest list has
 * ONE way in, and the couple shouldn't have to know in advance whether their file
 * is "a spreadsheet for the importer" or "a list for the assistant".
 */
export default function SheetPanel() {
  return (
    <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, p: 2 }}>
      <Stack direction="row" spacing={1.5} useFlexGap flexWrap="wrap" alignItems="center">
        <Typography variant="subtitle2" sx={{ mr: 1 }}>
          Spreadsheet
        </Typography>
        <Button
          size="small"
          variant="outlined"
          startIcon={<DownloadIcon />}
          onClick={() => downloadXlsx()}
        >
          Export by person
        </Button>
        <Button
          size="small"
          variant="outlined"
          startIcon={<DownloadIcon />}
          onClick={() => downloadTemplate()}
        >
          Blank template
        </Button>
        <Divider orientation="vertical" flexItem />
        <Stack direction="row" spacing={0.5} alignItems="center">
          <Typography variant="caption" color="text.secondary">
            Edit it, then bring it back through <b>Add my guest list</b> above.
          </Typography>
          <Tooltip
            arrow
            title={
              <Box sx={{ p: 0.5 }}>
                <Typography variant="caption" sx={{ fontWeight: 600, display: "block", mb: 0.5 }}>
                  How the sheet works
                </Typography>
                <Typography variant="caption" component="div" sx={{ lineHeight: 1.5 }}>
                  1. <b>Download</b> either <b>Export by person</b> (your live guest data) or a{" "}
                  <b>Blank template</b>.
                  <br />
                  2. <b>Fill it in Excel</b> — keep the same columns and layout (one row per person).
                  <br />
                  3. <b>Keep each family together</b> — a Primary row, then that party&apos;s{" "}
                  <i>Guest</i>/<i>Child</i> rows beneath it. Companion rows attach to the Primary
                  that shares their <b>Id</b> (the export fills the Id on every row), so you can
                  reorder whole families freely — just don&apos;t split a companion away from its
                  group.
                  <br />
                  4. <b>Drop it into the box above.</b> You&apos;ll see a preview of new/updated rows
                  before anything is saved.
                </Typography>
              </Box>
            }
          >
            <HelpOutlineIcon fontSize="small" sx={{ color: "text.secondary", cursor: "help" }} />
          </Tooltip>
        </Stack>
      </Stack>

      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
        <b>One row per person, grouped by party</b> — each invite&apos;s <i>Primary</i> row, then
        their <i>Guest</i>/<i>Child</i> rows beneath it. The <b>Id</b> (on every row of a party) is
        the invite&apos;s key: it ties companions to their Primary and is how an edited row updates
        the right invite — keep it to update an existing guest, leave it blank to add a new one (the
        Guest/Child rows aren&apos;t separate guests, so they share the Primary&apos;s Id). Edit a
        person&apos;s dietary/age on their own row, then re-import to bulk-update. <b>Greeting</b> is{" "}
        <b>required</b> on each Primary row — it&apos;s the invite&apos;s &quot;Dear …&quot; line and
        label (e.g. &quot;John &amp; Jane&quot;); the Name is optional. The <i>Guest</i>/<i>Child</i>{" "}
        <b>Name</b> rows pre-fill that invite&apos;s party, so the guest&apos;s RSVP opens with the
        +1/kids&apos; names ready to confirm (even before they reply). Set <b>Tier</b> (solo /
        plus_one / plus_family) to control their invite, and <b>Attending</b> = yes to import their
        RSVP + answers (the row&apos;s party replaces the stored one). <b>Expected</b> is your private
        pre-RSVP headcount estimate (0–50) — admin-only, never shown to the guest. <b>Actual</b> is
        the live RSVP head count — read-only, ignored on import.
      </Typography>
    </Box>
  );
}
