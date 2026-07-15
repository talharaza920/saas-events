"use client";

import { useCallback, useEffect, useState } from "react";
import NextLink from "next/link";

import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import Alert from "@mui/material/Alert";
import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Container from "@mui/material/Container";
import FormControlLabel from "@mui/material/FormControlLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Toolbar from "@mui/material/Toolbar";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import { AdminAuthError } from "@/lib/adminApi";
import {
  platformApi,
  type ApprovalItem,
  type AuditEntry,
  type PlanAdmin,
  type PlatformSettingsPayload,
  type PlatformStats,
  type PlatformUser,
  type PlatformWedding,
} from "@/lib/platformApi";
import SignInCard from "@/components/admin/SignInCard";
import AiConsoleTab from "@/components/platform/AiConsoleTab";
import ThemesTab from "@/components/platform/ThemesTab";

const STATUS_COLOR: Record<string, "default" | "info" | "success" | "warning" | "error"> = {
  draft: "default",
  pending_approval: "info",
  active: "success",
  suspended: "warning",
  archived: "error",
};

interface Data {
  weddings: PlatformWedding[];
  approvals: ApprovalItem[];
  users: PlatformUser[];
  plans: PlanAdmin[];
  rules: PlatformSettingsPayload;
  stats: PlatformStats;
  audit: AuditEntry[];
}

/**
 * The platform (super admin) console — RT's cockpit (SAAS_PLAN Phase 4).
 * Weddings + approval queue + users + plans/entitlements + auto-approval rules
 * + ops widgets, all against /api/platform/*.
 */
export default function PlatformPage() {
  const [data, setData] = useState<Data | null>(null);
  const [loading, setLoading] = useState(true);
  const [needsAuth, setNeedsAuth] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState(0);

  const load = useCallback(async () => {
    try {
      const [weddings, approvals, users, plans, rules, stats, audit] = await Promise.all([
        platformApi.weddings(),
        platformApi.approvals(),
        platformApi.users(),
        platformApi.plans(),
        platformApi.getApprovalSettings(),
        platformApi.stats(),
        platformApi.audit(50),
      ]);
      setData({ weddings, approvals, users, plans, rules, stats, audit });
      setNeedsAuth(false);
      setError(null);
    } catch (e) {
      if (e instanceof AdminAuthError) setNeedsAuth(true);
      else setError(e instanceof Error ? e.message : "Could not load the console.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: "grid", placeItems: "center", minHeight: "60vh" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (needsAuth || !data) {
    return (
      <SignInCard
        title="Platform console"
        subtitle="Platform-admin access required."
        error={error}
      />
    );
  }

  return (
    <Box>
      <AppBar position="static" color="default" elevation={0} sx={{ borderBottom: 1, borderColor: "divider" }}>
        <Toolbar sx={{ gap: 2 }}>
          <Button component={NextLink} href="/dashboard" startIcon={<ArrowBackIcon />} color="inherit">
            My weddings
          </Button>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            Platform console
          </Typography>
        </Toolbar>
      </AppBar>

      <Container maxWidth="lg" sx={{ py: 3 }}>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" scrollButtons="auto" sx={{ mb: 3 }}>
          <Tab label={`Weddings (${data.weddings.length})`} />
          <Tab label={`Approvals (${data.approvals.length})`} />
          <Tab label={`Users (${data.users.length})`} />
          <Tab label={`Plans (${data.plans.filter((p) => !p.archived).length})`} />
          <Tab label="Rules" />
          <Tab label="Ops" />
          <Tab label="AI" />
          <Tab label="Themes" />
        </Tabs>

        {tab === 0 && <WeddingsTab weddings={data.weddings} plans={data.plans} run={run} />}
        {tab === 1 && <ApprovalsTab approvals={data.approvals} run={run} />}
        {tab === 2 && <UsersTab users={data.users} run={run} />}
        {tab === 3 && <PlansTab plans={data.plans} run={run} />}
        {tab === 4 && <RulesTab rules={data.rules} run={run} />}
        {tab === 5 && <OpsTab stats={data.stats} audit={data.audit} />}
        {tab === 6 && <AiConsoleTab />}
        {tab === 7 && <ThemesTab />}
      </Container>
    </Box>
  );
}

type Run = (fn: () => Promise<unknown>) => Promise<void>;

function WeddingsTab({
  weddings,
  plans,
  run,
}: {
  weddings: PlatformWedding[];
  plans: PlanAdmin[];
  run: Run;
}) {
  return (
    <TableContainer component={Paper}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Wedding</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Owner</TableCell>
            <TableCell align="right">Members</TableCell>
            <TableCell align="right">Guests</TableCell>
            <TableCell>Plan</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {weddings.map((w) => (
            <TableRow key={w.id}>
              <TableCell>
                <Typography variant="body2">{w.couple_names}</Typography>
                <Typography variant="caption" color="text.secondary">
                  /{w.slug}
                </Typography>
              </TableCell>
              <TableCell>
                <Stack direction="row" spacing={0.5}>
                  <Chip
                    size="small"
                    label={w.status.replace("_", " ")}
                    color={STATUS_COLOR[w.status] ?? "default"}
                  />
                  {w.status === "active" && w.published && (
                    <Chip size="small" variant="outlined" label="live" color="success" />
                  )}
                </Stack>
              </TableCell>
              <TableCell>{w.owner_email ?? "—"}</TableCell>
              <TableCell align="right">{w.member_count}</TableCell>
              <TableCell align="right">{w.guest_count}</TableCell>
              <TableCell>
                <TextField
                  select
                  size="small"
                  variant="standard"
                  value={plans.find((p) => p.name === w.plan_name)?.id ?? ""}
                  onChange={(e) => run(() => platformApi.assignPlan(w.id, e.target.value || null))}
                  sx={{ minWidth: 100 }}
                >
                  <MenuItem value="">
                    <em>default</em>
                  </MenuItem>
                  {plans
                    .filter((p) => !p.archived)
                    .map((p) => (
                      <MenuItem key={p.id} value={p.id}>
                        {p.name}
                      </MenuItem>
                    ))}
                </TextField>
              </TableCell>
              <TableCell align="right">
                <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                  <Tooltip title="Open a read-only view via the wedding dashboard">
                    <Button size="small" component={NextLink} href={`/${w.slug}/admin`}>
                      View
                    </Button>
                  </Tooltip>
                  {(w.status === "pending_approval" || w.status === "draft") && (
                    <Button size="small" color="success" onClick={() => run(() => platformApi.approve(w.id))}>
                      Approve
                    </Button>
                  )}
                  {(w.status === "active" || w.status === "pending_approval") && (
                    <Button size="small" color="warning" onClick={() => run(() => platformApi.suspend(w.id))}>
                      Suspend
                    </Button>
                  )}
                  {(w.status === "suspended" || w.status === "archived") && (
                    <Button size="small" onClick={() => run(() => platformApi.reinstate(w.id))}>
                      Reinstate
                    </Button>
                  )}
                </Stack>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function ApprovalsTab({ approvals, run }: { approvals: ApprovalItem[]; run: Run }) {
  const [reasons, setReasons] = useState<Record<string, string>>({});
  if (approvals.length === 0) {
    return <Alert severity="success">The approval queue is empty.</Alert>;
  }
  return (
    <Stack spacing={2}>
      {approvals.map(({ wedding, rule_trace, would_auto_approve }) => (
        <Paper key={wedding.id} sx={{ p: 2 }}>
          <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
            <Box sx={{ flexGrow: 1 }}>
              <Typography variant="subtitle1">{wedding.couple_names}</Typography>
              <Typography variant="caption" color="text.secondary">
                /{wedding.slug} · {wedding.owner_email ?? "unknown owner"} · {wedding.guest_count} guests
              </Typography>
            </Box>
            {would_auto_approve && <Chip size="small" color="success" label="rules pass" />}
            <Button size="small" variant="contained" color="success" onClick={() => run(() => platformApi.approve(wedding.id))}>
              Approve
            </Button>
            <TextField
              size="small"
              placeholder="Denial reason"
              value={reasons[wedding.id] ?? ""}
              onChange={(e) => setReasons((r) => ({ ...r, [wedding.id]: e.target.value }))}
            />
            <Button
              size="small"
              color="error"
              disabled={!(reasons[wedding.id] ?? "").trim()}
              onClick={() => run(() => platformApi.deny(wedding.id, reasons[wedding.id].trim()))}
            >
              Deny
            </Button>
          </Stack>
          <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
            {rule_trace.map((t) => (
              <Tooltip key={t.rule} title={t.detail ?? ""}>
                <Chip
                  size="small"
                  variant="outlined"
                  label={t.rule.replace(/_/g, " ")}
                  color={t.ok ? "success" : "error"}
                />
              </Tooltip>
            ))}
          </Stack>
        </Paper>
      ))}
    </Stack>
  );
}

function UsersTab({ users, run }: { users: PlatformUser[]; run: Run }) {
  return (
    <TableContainer component={Paper}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>User</TableCell>
            <TableCell align="right">Weddings</TableCell>
            <TableCell>Flags</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {users.map((u) => (
            <TableRow key={u.user_id}>
              <TableCell>
                {u.display_name ? `${u.display_name} — ` : ""}
                {u.email}
              </TableCell>
              <TableCell align="right">{u.wedding_count}</TableCell>
              <TableCell>
                <Stack direction="row" spacing={0.5}>
                  {u.is_platform_admin && <Chip size="small" color="primary" label="platform admin" />}
                  {u.disabled && <Chip size="small" color="error" label="disabled" />}
                </Stack>
              </TableCell>
              <TableCell align="right">
                <Button
                  size="small"
                  color={u.disabled ? "success" : "error"}
                  onClick={() => run(() => platformApi.setUserDisabled(u.user_id, !u.disabled))}
                >
                  {u.disabled ? "Enable" : "Disable"}
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function PlansTab({ plans, run }: { plans: PlanAdmin[]; run: Run }) {
  const [name, setName] = useState("");
  const [entitlementsJson, setEntitlementsJson] = useState('{\n  "max_guests": 50\n}');
  const [jsonError, setJsonError] = useState<string | null>(null);

  const create = () => {
    try {
      const entitlements = JSON.parse(entitlementsJson);
      setJsonError(null);
      run(() => platformApi.createPlan({ name: name.trim(), entitlements }));
      setName("");
    } catch {
      setJsonError("Entitlements must be valid JSON");
    }
  };

  return (
    <Stack spacing={2}>
      <Paper sx={{ p: 2 }}>
        <Typography variant="subtitle1" gutterBottom>
          New plan
        </Typography>
        <Stack spacing={2}>
          <TextField label="Name" size="small" value={name} onChange={(e) => setName(e.target.value)} sx={{ maxWidth: 300 }} />
          <TextField
            label="Entitlements (JSON)"
            size="small"
            multiline
            minRows={3}
            value={entitlementsJson}
            onChange={(e) => setEntitlementsJson(e.target.value)}
            error={Boolean(jsonError)}
            helperText={jsonError ?? 'Keys: max_guests, max_members, max_custom_questions, max_story_arcs, wishes_enabled, export_enabled, import_enabled, …'}
            sx={{ fontFamily: "monospace" }}
          />
          <Box>
            <Button variant="contained" size="small" disabled={!name.trim()} onClick={create}>
              Create plan
            </Button>
          </Box>
        </Stack>
      </Paper>

      <TableContainer component={Paper}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Plan</TableCell>
              <TableCell>Entitlements</TableCell>
              <TableCell>Default</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {plans.map((p) => (
              <TableRow key={p.id} sx={p.archived ? { opacity: 0.5 } : undefined}>
                <TableCell>{p.name}</TableCell>
                <TableCell>
                  <Typography variant="caption" component="code" sx={{ fontFamily: "monospace" }}>
                    {JSON.stringify(p.entitlements)}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Checkbox
                    size="small"
                    checked={p.is_default}
                    disabled={p.archived}
                    onChange={(_, checked) =>
                      run(() => platformApi.updatePlan(p.id, { is_default: checked }))
                    }
                  />
                </TableCell>
                <TableCell align="right">
                  <Button
                    size="small"
                    color={p.archived ? "success" : "error"}
                    onClick={() => run(() => platformApi.updatePlan(p.id, { archived: !p.archived }))}
                  >
                    {p.archived ? "Restore" : "Archive"}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Stack>
  );
}

function RulesTab({ rules, run }: { rules: PlatformSettingsPayload; run: Run }) {
  const [form, setForm] = useState<PlatformSettingsPayload>(rules);
  const [bannedText, setBannedText] = useState((rules.banned_words ?? []).join(", "));

  return (
    <Paper sx={{ p: 3, maxWidth: 560 }}>
      <Typography variant="subtitle1" gutterBottom>
        Auto-approval rules
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        When auto-approval is on, a submission that passes every rule activates instantly;
        anything else queues for manual review.
      </Typography>
      <Stack spacing={2}>
        <FormControlLabel
          control={
            <Checkbox
              checked={form.auto_approve ?? false}
              onChange={(_, v) => setForm((f) => ({ ...f, auto_approve: v }))}
            />
          }
          label="Auto-approve submissions that pass all rules"
        />
        <TextField
          label="Minimum account age (hours)"
          type="number"
          size="small"
          value={form.min_account_age_hours ?? 0}
          onChange={(e) => setForm((f) => ({ ...f, min_account_age_hours: Number(e.target.value) }))}
        />
        <TextField
          label="Max weddings per account"
          type="number"
          size="small"
          value={form.max_weddings_per_account ?? 3}
          onChange={(e) => setForm((f) => ({ ...f, max_weddings_per_account: Number(e.target.value) }))}
        />
        <TextField
          label="Max guests at submission"
          type="number"
          size="small"
          value={form.max_guests_at_submission ?? 500}
          onChange={(e) => setForm((f) => ({ ...f, max_guests_at_submission: Number(e.target.value) }))}
        />
        <TextField
          label="Banned words (comma-separated)"
          size="small"
          value={bannedText}
          onChange={(e) => setBannedText(e.target.value)}
        />
        <Box>
          <Button
            variant="contained"
            size="small"
            onClick={() =>
              run(() =>
                platformApi.putApprovalSettings({
                  ...form,
                  banned_words: bannedText
                    .split(",")
                    .map((w) => w.trim())
                    .filter(Boolean),
                }),
              )
            }
          >
            Save rules
          </Button>
        </Box>
      </Stack>
    </Paper>
  );
}

function OpsTab({ stats, audit }: { stats: PlatformStats; audit: AuditEntry[] }) {
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
        {Object.entries(stats.weddings_by_status ?? {}).map(([status, count]) => (
          <Paper key={status} sx={{ p: 2, minWidth: 130 }}>
            <Typography variant="h5">{count}</Typography>
            <Typography variant="caption" color="text.secondary">
              {status.replace("_", " ")}
            </Typography>
          </Paper>
        ))}
        <Paper sx={{ p: 2, minWidth: 130 }}>
          <Typography variant="h5">{stats.total_users}</Typography>
          <Typography variant="caption" color="text.secondary">
            users
          </Typography>
        </Paper>
        <Paper sx={{ p: 2, minWidth: 130 }}>
          <Typography variant="h5">{stats.total_guests}</Typography>
          <Typography variant="caption" color="text.secondary">
            guests
          </Typography>
        </Paper>
        <Paper sx={{ p: 2, minWidth: 130 }}>
          <Typography variant="h5">{stats.rsvps_last_7_days}</Typography>
          <Typography variant="caption" color="text.secondary">
            RSVPs / 7d
          </Typography>
        </Paper>
        <Paper sx={{ p: 2, minWidth: 130 }}>
          <Typography variant="h5">{stats.signups_last_7_days}</Typography>
          <Typography variant="caption" color="text.secondary">
            signups / 7d
          </Typography>
        </Paper>
      </Stack>

      <TableContainer component={Paper}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>When</TableCell>
              <TableCell>Actor</TableCell>
              <TableCell>Action</TableCell>
              <TableCell>Detail</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {audit.map((a) => (
              <TableRow key={a.id}>
                <TableCell>
                  <Typography variant="caption">
                    {a.created_at ? new Date(a.created_at).toLocaleString() : "—"}
                  </Typography>
                </TableCell>
                <TableCell>{a.actor_email ?? "system"}</TableCell>
                <TableCell>
                  <code>{a.action}</code>
                </TableCell>
                <TableCell>
                  <Typography variant="caption" sx={{ fontFamily: "monospace" }}>
                    {JSON.stringify(a.detail)}
                  </Typography>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Stack>
  );
}
