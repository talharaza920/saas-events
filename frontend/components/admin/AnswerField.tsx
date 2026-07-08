"use client";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import type { AnswerValue, QuestionAdmin } from "@/lib/adminApi";

/** Is this question answered (used for required-validation + which answers to send). */
export function isAnswered(q: QuestionAdmin, v: AnswerValue | undefined): boolean {
  if (!v) return false;
  if (q.qtype === "text") return typeof v.text === "string" && v.text.trim() !== "";
  if (q.qtype === "number") return typeof v.number === "number" && !Number.isNaN(v.number);
  if (q.qtype === "choice") return typeof v.choice === "string" && v.choice !== "";
  if (q.qtype === "multi_choice") return Array.isArray(v.choices) && v.choices.length > 0;
  if (q.qtype === "yesno") return typeof v.yesno === "boolean";
  return false;
}

/** One answer editor, by question type. Shared by the companion + guest dialogs. */
export default function AnswerField({
  question,
  value,
  onChange,
}: {
  question: QuestionAdmin;
  value: AnswerValue | undefined;
  onChange: (v: AnswerValue) => void;
}) {
  const label = question.required ? `${question.prompt} *` : question.prompt;
  const options = (question.options as unknown[]).map((o) => String(o));

  if (question.qtype === "number") {
    return (
      <TextField
        label={label}
        value={value?.number != null ? String(value.number) : ""}
        onChange={(e) => {
          const digits = e.target.value.replace(/[^0-9]/g, "");
          onChange(digits === "" ? {} : { number: Number(digits) });
        }}
        inputMode="numeric"
        fullWidth
      />
    );
  }

  if (question.qtype === "choice") {
    return (
      <TextField label={label} value={value?.choice ?? ""} onChange={(e) => onChange({ choice: e.target.value })} select fullWidth>
        {options.map((opt) => (
          <MenuItem key={opt} value={opt}>
            {opt}
          </MenuItem>
        ))}
      </TextField>
    );
  }

  if (question.qtype === "multi_choice") {
    const chosen = Array.isArray(value?.choices) ? value!.choices! : [];
    const toggle = (opt: string) =>
      onChange({ choices: chosen.includes(opt) ? chosen.filter((c) => c !== opt) : [...chosen, opt] });
    return (
      <Box>
        <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
          {label}
        </Typography>
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
          {options.map((opt) => (
            <Chip
              key={opt}
              label={opt}
              size="small"
              color={chosen.includes(opt) ? "primary" : "default"}
              variant={chosen.includes(opt) ? "filled" : "outlined"}
              onClick={() => toggle(opt)}
            />
          ))}
        </Box>
      </Box>
    );
  }

  if (question.qtype === "yesno") {
    const current = typeof value?.yesno === "boolean" ? value.yesno : "";
    return (
      <TextField
        label={label}
        value={current === "" ? "" : current ? "yes" : "no"}
        onChange={(e) => onChange({ yesno: e.target.value === "yes" })}
        select
        fullWidth
      >
        <MenuItem value="yes">Yes</MenuItem>
        <MenuItem value="no">No</MenuItem>
      </TextField>
    );
  }

  // text
  return (
    <TextField label={label} value={value?.text ?? ""} onChange={(e) => onChange({ text: e.target.value })} fullWidth multiline minRows={1} />
  );
}
