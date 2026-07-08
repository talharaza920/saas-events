"use client";

import { useState } from "react";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { adminApi, type AdminMe, type MemberAdmin } from "@/lib/adminApi";

/**
 * Members tab (Phase 3): the wedding's team. Any member can view; only the owner
 * sees the invite/revoke/transfer controls (the backend enforces it regardless).
 * A fresh invite surfaces its accept link so the owner can copy it into any
 * channel — it only works for the invited email.
 */
export default function MembersPanel({
  me,
  members,
  onChanged,
}: {
  me: AdminMe;
  members: MemberAdmin[];
  onChanged: () => Promise<void> | void;
}) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"admin" | "owner">("admin");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [acceptPath, setAcceptPath] = useState<string | null>(null);
  const [transferTarget, setTransferTarget] = useState<MemberAdmin | null>(null);

  const isOwner = me.role === "owner" || me.role === "platform";

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack spacing={2}>
      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {acceptPath && (
        <Alert severity="success" onClose={() => setAcceptPath(null)}>
          Invite sent. Accept link (works only for that email):{" "}
          <code>{typeof window !== "undefined" ? window.location.origin + acceptPath : acceptPath}</code>
        </Alert>
      )}

      {isOwner && (
        <Paper sx={{ p: 2 }}>
          <Typography variant="subtitle1" gutterBottom>
            Invite a co-admin
          </Typography>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField
              label="Email"
              size="small"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              sx={{ minWidth: 260 }}
            />
            <TextField
              select
              label="Role"
              size="small"
              value={role}
              onChange={(e) => setRole(e.target.value as "admin" | "owner")}
              sx={{ minWidth: 140 }}
            >
              <MenuItem value="admin">Admin</MenuItem>
              <MenuItem value="owner">Owner</MenuItem>
            </TextField>
            <Button
              variant="contained"
              disabled={busy || !email.trim()}
              onClick={() =>
                run(async () => {
                  const res = await adminApi.inviteMember(email.trim(), role);
                  setAcceptPath(res.accept_path);
                  setEmail("");
                })
              }
            >
              Send invite
            </Button>
          </Stack>
          <Typography variant="caption" color="text.secondary">
            They sign in with that email, then open the invite link. Invites expire in 7 days.
          </Typography>
        </Paper>
      )}

      <Paper>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Member</TableCell>
              <TableCell>Role</TableCell>
              <TableCell>Status</TableCell>
              {isOwner && <TableCell align="right">Actions</TableCell>}
            </TableRow>
          </TableHead>
          <TableBody>
            {members.map((m) => (
              <TableRow key={m.id}>
                <TableCell>
                  {m.display_name ? `${m.display_name} — ` : ""}
                  {m.email}
                </TableCell>
                <TableCell>
                  <Chip size="small" label={m.role} color={m.role === "owner" ? "primary" : "default"} />
                </TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    variant="outlined"
                    label={m.status}
                    color={
                      m.status === "active" ? "success" : m.status === "invited" ? "info" : "default"
                    }
                  />
                </TableCell>
                {isOwner && (
                  <TableCell align="right">
                    {m.status === "active" && m.role !== "owner" && (
                      <Button size="small" disabled={busy} onClick={() => setTransferTarget(m)}>
                        Make owner
                      </Button>
                    )}
                    {m.status !== "revoked" && (
                      <Button
                        size="small"
                        color="error"
                        disabled={busy}
                        onClick={() => run(() => adminApi.revokeMember(m.id))}
                      >
                        {m.status === "invited" ? "Cancel invite" : "Remove"}
                      </Button>
                    )}
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>

      {/* Two-step confirm for ownership transfer. */}
      <Dialog open={transferTarget !== null} onClose={() => setTransferTarget(null)}>
        <DialogTitle>Transfer ownership?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {transferTarget?.email} becomes the owner of this wedding and you step down to admin.
            Only they can undo this.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTransferTarget(null)}>Cancel</Button>
          <Button
            color="error"
            onClick={() => {
              const target = transferTarget;
              setTransferTarget(null);
              if (target) run(() => adminApi.transferOwnership(target.id));
            }}
          >
            Transfer
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
