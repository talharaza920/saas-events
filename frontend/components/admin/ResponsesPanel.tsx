"use client";

import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { formatAnswer, type AnswerAdmin, type ResponseAdmin } from "@/lib/adminApi";

/** A person's answers as "Prompt: value" lines (skips blanks). */
function answerLines(answers: AnswerAdmin[]): { key: string; text: string }[] {
  return answers
    .map((a) => ({ key: a.question_id, prompt: a.prompt, value: formatAnswer(a.value) }))
    .filter((a) => a.value)
    .map((a) => ({ key: a.key, text: `${a.prompt}: ${a.value}` }));
}

/** "Updated 14 Jun · entered by you (owner@…)" — where/when the RSVP last changed. */
function provenance(r: ResponseAdmin): string {
  const when = r.updated_at ?? r.responded_at;
  if (!when) return "";
  const dt = new Date(when).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
  const via =
    r.last_source === "admin"
      ? "entered/edited by the couple"
      : r.last_source === "import"
        ? "imported"
        : "replied by guest";
  const actor = r.last_actor ? ` (${r.last_actor})` : "";
  return `Updated ${dt} · ${via}${actor}`;
}

export default function ResponsesPanel({ responses }: { responses: ResponseAdmin[] }) {
  if (responses.length === 0) {
    return <Typography color="text.secondary">No RSVPs submitted yet.</Typography>;
  }

  return (
    <Stack spacing={1}>
      {responses.map((r) => (
        <Accordion key={r.guest_id} variant="outlined" disableGutters>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexGrow: 1 }}>
              <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                <Typography sx={{ fontWeight: 600 }}>{r.guest_name}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {provenance(r)}
                </Typography>
              </Box>
              <Chip
                size="small"
                color={r.attending ? "success" : "error"}
                label={r.attending ? "Attending" : "Declined"}
              />
              {r.attending && r.companions.length > 0 && (
                <Chip size="small" variant="outlined" label={`+${r.companions.length}`} />
              )}
            </Box>
          </AccordionSummary>
          <AccordionDetails>
            <Stack spacing={1.5} divider={<Divider flexItem />}>
              {answerLines(r.answers).length > 0 && (
                <Box>
                  <Typography variant="body2" fontWeight={600} gutterBottom>
                    {r.guest_name}
                  </Typography>
                  {answerLines(r.answers).map((a) => (
                    <Typography key={a.key} variant="body2" color="text.secondary">
                      • {a.text}
                    </Typography>
                  ))}
                </Box>
              )}
              {r.companions.length > 0 && (
                <Box>
                  <Typography variant="body2" fontWeight={600} gutterBottom>
                    Companions
                  </Typography>
                  {r.companions.map((c, i) => (
                    <Box key={i} sx={{ mb: 0.5 }}>
                      <Typography variant="body2" color="text.secondary">
                        • {c.kind}: {c.name || "(unnamed)"}
                      </Typography>
                      {answerLines(c.answers).map((a) => (
                        <Typography key={a.key} variant="caption" color="text.secondary" sx={{ display: "block", pl: 2 }}>
                          {a.text}
                        </Typography>
                      ))}
                    </Box>
                  ))}
                </Box>
              )}
              {r.notes && (
                <Typography variant="body2">
                  <strong>Notes:</strong> {r.notes}
                </Typography>
              )}
            </Stack>
          </AccordionDetails>
        </Accordion>
      ))}
    </Stack>
  );
}
