"use client";

import { useCallback, useEffect, useState } from "react";

import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import FormControlLabel from "@mui/material/FormControlLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import {
  platformApi,
  type AiPromptAdmin,
  type AiSettingsPayload,
  type AiSettingsView,
  type AiUsageSummary,
} from "@/lib/platformApi";

const usd = (v: number) => `$${v.toFixed(2)}`;

/**
 * The AI console (AI_WIZARD_PLAN 8.2 + guardrail 10): the circuit breaker, the
 * text model, spend widgets, and the prompt registry editor. Prompts and models
 * are the trust boundary the plan reserves for platform admins — prompt saves
 * create a NEW version (never in-place), rollback = deactivate (resolution falls
 * back provider row → shared row → code default, so nothing ever bricks the
 * pipeline); the model choice falls back to the deployed env default the same
 * way when a field is cleared.
 */
export default function AiConsoleTab() {
  const [settings, setSettings] = useState<AiSettingsView | null>(null);
  const [usage, setUsage] = useState<AiUsageSummary | null>(null);
  const [prompts, setPrompts] = useState<AiPromptAdmin[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, u, p] = await Promise.all([
        platformApi.getAiSettings(),
        platformApi.aiUsage(),
        platformApi.aiPrompts(),
      ]);
      setSettings(s);
      setUsage(u);
      setPrompts(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the AI console.");
    }
  }, []);

  useEffect(() => {
    // Fetch-on-mount: setState happens after load()'s first await.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  if (!settings || !usage || !prompts) {
    return error ? (
      <Alert severity="error">{error}</Alert>
    ) : (
      <Box sx={{ display: "grid", placeItems: "center", py: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

  // The breaker and the model share ONE settings row and the PUT is whole-blob,
  // so a card that sent only its own fields would silently wipe the other's.
  // Both cards save through here instead.
  const save = (patch: Partial<AiSettingsPayload>) =>
    run(() =>
      platformApi.putAiSettings({
        kill_switch: settings.kill_switch,
        daily_cost_ceiling_usd: settings.daily_cost_ceiling_usd,
        text_provider: settings.text_provider,
        text_model: settings.text_model,
        text_effort: settings.text_effort,
        ...patch,
      }),
    );

  return (
    <Stack spacing={3}>
      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      <BreakerCard settings={settings} busy={busy} save={save} />
      <ModelCard settings={settings} busy={busy} save={save} />
      <UsageCard usage={usage} />
      <PromptsCard prompts={prompts} busy={busy} run={run} />
    </Stack>
  );
}

type Run = (fn: () => Promise<unknown>) => Promise<void>;
type Save = (patch: Partial<AiSettingsPayload>) => Promise<void>;

// --- Text model --------------------------------------------------------------
function ModelCard({
  settings,
  busy,
  save,
}: {
  settings: AiSettingsView;
  busy: boolean;
  save: Save;
}) {
  const [provider, setProvider] = useState(settings.text_provider ?? "");
  const [model, setModel] = useState(settings.text_model ?? "");
  const [effort, setEffort] = useState(settings.text_effort ?? "");
  const missingKey =
    provider !== "" && settings.keys_configured?.[provider] === false;

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Stack spacing={2}>
        <Typography variant="subtitle1">Text model</Typography>
        {!settings.live_calls && (
          <Alert severity="info">
            This environment has live AI calls switched off, so the offline demo model is
            answering every run — whatever is selected below. Nothing here is being called.
          </Alert>
        )}
        <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }} useFlexGap>
          <Chip
            color={settings.live_calls ? "primary" : "default"}
            variant="outlined"
            label={`${settings.live_calls ? "Live" : "Selected"}: ${settings.effective_provider} / ${settings.effective_model} · ${settings.effective_effort}`}
          />
          <Chip
            size="small"
            variant="outlined"
            label={settings.from_env ? "from deployed default" : "overridden here"}
          />
        </Stack>
        <Typography variant="body2" color="text.secondary">
          Overrides the deployed default platform-wide, for every wedding — model ids change
          faster than deploys. Leave a field blank to fall back to what&apos;s deployed. The
          model must match the provider&apos;s family, and a value this app can&apos;t use is
          ignored rather than allowed to break every run.
        </Typography>
        {missingKey && (
          <Alert severity="warning">
            No API key is configured for <strong>{provider}</strong> in this environment — runs
            would fail. Add the key before switching.
          </Alert>
        )}
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
          <TextField
            select
            label="Provider"
            value={provider}
            onChange={(e) => setProvider(e.target.value as typeof provider)}
            sx={{ minWidth: 180 }}
            helperText="Blank = deployed default"
          >
            <MenuItem value="">deployed default</MenuItem>
            <MenuItem value="anthropic">anthropic</MenuItem>
            <MenuItem value="openai">openai</MenuItem>
          </TextField>
          <TextField
            label="Model"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            sx={{ minWidth: 240 }}
            helperText="Blank = that provider's default"
          />
          <TextField
            select
            label="Effort"
            value={effort}
            onChange={(e) => setEffort(e.target.value as typeof effort)}
            sx={{ minWidth: 140 }}
          >
            <MenuItem value="">deployed default</MenuItem>
            <MenuItem value="low">low</MenuItem>
            <MenuItem value="medium">medium</MenuItem>
            <MenuItem value="high">high</MenuItem>
          </TextField>
        </Stack>
        <Typography variant="caption" color="text.secondary">
          To stop AI entirely, use the kill switch — it fails closed. (Whether this deployment
          may call a provider at all is an environment setting, deliberately not editable here:
          a stop switch that needs the database is a stop switch that fails when you need it.)
        </Typography>
        <Box>
          <Button
            variant="contained"
            disabled={busy}
            onClick={() =>
              save({
                text_provider: provider as AiSettingsPayload["text_provider"],
                text_model: model.trim(),
                text_effort: effort as AiSettingsPayload["text_effort"],
              })
            }
          >
            Save
          </Button>
        </Box>
      </Stack>
    </Paper>
  );
}

// --- Circuit breaker ---------------------------------------------------------
function BreakerCard({ settings, busy, save }: { settings: AiSettingsView; busy: boolean; save: Save }) {
  const [kill, setKill] = useState(Boolean(settings.kill_switch));
  const [ceiling, setCeiling] = useState(String(settings.daily_cost_ceiling_usd ?? 0));
  const ceilingNum = Number.parseFloat(ceiling);
  const valid = Number.isFinite(ceilingNum) && ceilingNum >= 0;

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Stack spacing={2}>
        <Typography variant="subtitle1">Circuit breaker</Typography>
        {kill && (
          <Alert severity="warning">
            The kill switch is ON — every AI call is refused platform-wide until it&apos;s turned
            off.
          </Alert>
        )}
        <FormControlLabel
          control={<Switch checked={kill} onChange={(e) => setKill(e.target.checked)} />}
          label="Kill switch (pause all AI assistance)"
        />
        <TextField
          label="Daily cost ceiling (USD)"
          value={ceiling}
          onChange={(e) => setCeiling(e.target.value)}
          error={!valid}
          helperText={
            valid
              ? "Past this, runs queue (never fail) until the next UTC day. 0 disables the ceiling."
              : "Enter a number ≥ 0"
          }
          sx={{ maxWidth: 280 }}
        />
        <Box>
          <Button
            variant="contained"
            disabled={busy || !valid}
            onClick={() => save({ kill_switch: kill, daily_cost_ceiling_usd: ceilingNum })}
          >
            Save
          </Button>
        </Box>
      </Stack>
    </Paper>
  );
}

// --- Usage widgets -----------------------------------------------------------
function UsageCard({ usage }: { usage: AiUsageSummary }) {
  const days = [...usage.days].reverse(); // newest first for the table
  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Stack spacing={2}>
        <Typography variant="subtitle1">Usage — last 30 days</Typography>
        <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }} useFlexGap>
          <Chip label={`Today: ${usd(usage.today_usd)}`} color="primary" variant="outlined" />
          <Chip
            label={
              usage.ceiling_usd > 0 ? `Ceiling: ${usd(usage.ceiling_usd)}/day` : "No daily ceiling"
            }
            variant="outlined"
          />
          {Object.entries(usage.jobs_by_status ?? {}).map(([k, v]) => (
            <Chip key={k} size="small" variant="outlined" label={`${k.replace(/_/g, " ")}: ${v}`} />
          ))}
        </Stack>

        <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="caption" color="text.secondary">
              Spend by step
            </Typography>
            <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", mt: 0.5 }} useFlexGap>
              {Object.entries(usage.by_kind ?? {}).map(([k, v]) => (
                <Chip key={k} size="small" label={`${k}: ${usd(v)}`} />
              ))}
            </Stack>
          </Box>
          <Box sx={{ flex: 1 }}>
            <Typography variant="caption" color="text.secondary">
              Spend by provider
            </Typography>
            <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", mt: 0.5 }} useFlexGap>
              {Object.entries(usage.by_provider ?? {}).map(([k, v]) => (
                <Chip key={k} size="small" label={`${k}: ${usd(v)}`} />
              ))}
            </Stack>
          </Box>
        </Stack>

        {usage.top_weddings.length > 0 && (
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Top spenders</TableCell>
                  <TableCell align="right">30-day spend</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {usage.top_weddings.map((w) => (
                  <TableRow key={w.wedding_id}>
                    <TableCell>{w.slug ?? w.wedding_id}</TableCell>
                    <TableCell align="right">{usd(w.usd)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}

        {days.length > 0 && (
          <TableContainer sx={{ maxHeight: 260 }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell>Day (UTC)</TableCell>
                  <TableCell align="right">Calls</TableCell>
                  <TableCell align="right">Spend</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {days.map((d) => (
                  <TableRow key={d.date}>
                    <TableCell>{d.date}</TableCell>
                    <TableCell align="right">{d.calls}</TableCell>
                    <TableCell align="right">{usd(d.usd)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Stack>
    </Paper>
  );
}

// --- Prompt registry ----------------------------------------------------------
function PromptsCard({ prompts, busy, run }: { prompts: AiPromptAdmin[]; busy: boolean; run: Run }) {
  const keys = Array.from(new Set(prompts.map((p) => p.key))).sort();
  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Stack spacing={2}>
        <Typography variant="subtitle1">Prompt registry</Typography>
        <Typography variant="body2" color="text.secondary">
          Saving creates a <strong>new version</strong> and activates it; rollback = deactivate a
          row (resolution falls back provider row → shared row → the code default, so the
          pipeline can never be bricked from here). Version 0 is the code default.
        </Typography>
        {keys.map((key) => (
          <PromptKeyEditor key={key} promptKey={key} rows={prompts.filter((p) => p.key === key)} busy={busy} run={run} />
        ))}
      </Stack>
    </Paper>
  );
}

function PromptKeyEditor({
  promptKey,
  rows,
  busy,
  run,
}: {
  promptKey: string;
  rows: AiPromptAdmin[];
  busy: boolean;
  run: Run;
}) {
  const effective = rows.find((r) => r.is_effective);
  const [form, setForm] = useState(() => ({
    template: effective?.template ?? "",
    provider: "" as "" | "anthropic" | "openai",
    model: "",
    effort: "" as "" | "low" | "medium" | "high",
    max_tokens: "",
  }));
  const maxTokensNum = Number.parseInt(form.max_tokens, 10);

  return (
    <Accordion variant="outlined" disableGutters>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
          <Typography sx={{ fontFamily: "monospace" }}>{promptKey}</Typography>
          {effective && (
            <Chip
              size="small"
              color="success"
              variant="outlined"
              label={`live: v${effective.version}${effective.provider ? ` (${effective.provider})` : effective.version === 0 ? " (code)" : ""}`}
            />
          )}
        </Stack>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={2}>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Version</TableCell>
                  <TableCell>Provider</TableCell>
                  <TableCell>Model / effort / max tokens</TableCell>
                  <TableCell>Updated</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={`${r.provider}:${r.version}`} selected={r.is_effective}>
                    <TableCell>
                      v{r.version}
                      {r.is_code_default && " (code default)"}
                      {r.is_effective && (
                        <Chip size="small" color="success" label="live" sx={{ ml: 1 }} />
                      )}
                      {!r.active && !r.is_code_default && (
                        <Chip size="small" variant="outlined" label="inactive" sx={{ ml: 1 }} />
                      )}
                    </TableCell>
                    <TableCell>{r.provider || "shared"}</TableCell>
                    <TableCell>
                      {[r.model, r.effort, r.max_tokens].filter(Boolean).join(" / ") || "—"}
                    </TableCell>
                    <TableCell>
                      {r.updated_by ? `${r.updated_by} · ` : ""}
                      {r.updated_at ? new Date(r.updated_at).toLocaleDateString() : "—"}
                    </TableCell>
                    <TableCell align="right">
                      <Stack direction="row" spacing={1} sx={{ justifyContent: "flex-end" }}>
                        <Button
                          size="small"
                          onClick={() =>
                            setForm({
                              template: r.template,
                              provider: (r.provider as "" | "anthropic" | "openai") ?? "",
                              model: r.model ?? "",
                              effort: (r.effort as "" | "low" | "medium" | "high") ?? "",
                              max_tokens: r.max_tokens ? String(r.max_tokens) : "",
                            })
                          }
                        >
                          Load
                        </Button>
                        {!r.is_code_default && (
                          <Button
                            size="small"
                            color={r.active ? "warning" : "primary"}
                            disabled={busy}
                            onClick={() =>
                              run(() =>
                                platformApi.activateAiPrompt(promptKey, r.provider, r.version, !r.active),
                              )
                            }
                          >
                            {r.active ? "Deactivate" : "Activate"}
                          </Button>
                        )}
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          <Typography variant="caption" color="text.secondary">
            Edit below and save as a new version. Allowlisted ${"{variables}"} only — anything
            else is refused at render time.
          </Typography>
          <TextField
            multiline
            minRows={6}
            fullWidth
            label="Template"
            value={form.template}
            onChange={(e) => setForm({ ...form, template: e.target.value })}
            slotProps={{ input: { sx: { fontFamily: "monospace", fontSize: 13 } } }}
          />
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField
              select
              label="Provider"
              value={form.provider}
              onChange={(e) => setForm({ ...form, provider: e.target.value as typeof form.provider })}
              sx={{ minWidth: 160 }}
              helperText="Shared = all providers"
            >
              <MenuItem value="">shared</MenuItem>
              <MenuItem value="anthropic">anthropic</MenuItem>
              <MenuItem value="openai">openai</MenuItem>
            </TextField>
            <TextField
              label="Model override"
              value={form.model}
              onChange={(e) => setForm({ ...form, model: e.target.value })}
              sx={{ minWidth: 200 }}
              helperText="Empty = configured default"
            />
            <TextField
              select
              label="Effort"
              value={form.effort}
              onChange={(e) => setForm({ ...form, effort: e.target.value as typeof form.effort })}
              sx={{ minWidth: 120 }}
            >
              <MenuItem value="">default</MenuItem>
              <MenuItem value="low">low</MenuItem>
              <MenuItem value="medium">medium</MenuItem>
              <MenuItem value="high">high</MenuItem>
            </TextField>
            <TextField
              label="Max tokens"
              value={form.max_tokens}
              onChange={(e) => setForm({ ...form, max_tokens: e.target.value })}
              sx={{ minWidth: 120 }}
              helperText="Empty = default"
            />
          </Stack>
          <Box>
            <Button
              variant="contained"
              disabled={busy || !form.template.trim()}
              onClick={() =>
                run(() =>
                  platformApi.saveAiPrompt(promptKey, {
                    template: form.template,
                    provider: form.provider,
                    model: form.model.trim() || null,
                    effort: form.effort || null,
                    max_tokens: Number.isFinite(maxTokensNum) && maxTokensNum > 0 ? maxTokensNum : null,
                  }),
                )
              }
            >
              Save as new version
            </Button>
          </Box>
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}
