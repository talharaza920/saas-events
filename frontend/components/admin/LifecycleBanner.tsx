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
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import FormControlLabel from "@mui/material/FormControlLabel";
import Typography from "@mui/material/Typography";

import { adminApi, type AdminMe } from "@/lib/adminApi";

const STATUS_LABEL: Record<string, string> = {
  draft: "Draft",
  pending_approval: "Pending approval",
  active: "Approved",
  suspended: "Suspended",
  archived: "Archived",
};

const STATUS_COLOR: Record<string, "default" | "info" | "success" | "warning" | "error"> = {
  draft: "default",
  pending_approval: "info",
  active: "success",
  suspended: "warning",
  archived: "error",
};

/**
 * The dashboard's lifecycle strip: status chip, publish switch, and the
 * submit-for-approval / delete actions. Approval (status) and publication
 * (published) are independent switches — mirrors the backend exactly and
 * refreshes `me` after every transition.
 */
export default function LifecycleBanner({
  me,
  onChanged,
}: {
  me: AdminMe;
  onChanged: () => Promise<void> | void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const run = async (fn: () => Promise<unknown>, doneMsg?: string) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      if (doneMsg) setNotice(doneMsg);
      await onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  const isOwner = me.role === "owner" || me.role === "platform";

  return (
    <Stack spacing={1} sx={{ mb: 2 }}>
      {me.wedding_status === "suspended" && (
        <Alert severity="warning">
          This wedding is suspended — the dashboard is read-only. Contact the platform for help.
        </Alert>
      )}
      {me.wedding_status === "pending_approval" && (
        <Alert severity="info">
          Submitted for approval — you&apos;ll be able to publish once it&apos;s approved.
        </Alert>
      )}
      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {notice && (
        <Alert severity="success" onClose={() => setNotice(null)}>
          {notice}
        </Alert>
      )}

      <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
        <Chip
          label={STATUS_LABEL[me.wedding_status] ?? me.wedding_status}
          color={STATUS_COLOR[me.wedding_status] ?? "default"}
          size="small"
        />

        {me.wedding_status === "draft" && isOwner && (
          <Button
            size="small"
            variant="contained"
            disabled={busy}
            onClick={() =>
              run(
                () => adminApi.submitApproval(),
                "Submitted — you'll hear back once it's reviewed.",
              )
            }
          >
            Submit for approval
          </Button>
        )}

        {me.wedding_status === "active" && (
          <FormControlLabel
            control={
              <Switch
                size="small"
                checked={me.published}
                disabled={busy || !me.can_publish}
                onChange={(_, checked) =>
                  run(
                    () => adminApi.setPublished(checked),
                    checked
                      ? "Published — guest links are live."
                      : "Unpublished — guest links are dark.",
                  )
                }
              />
            }
            label={
              <Typography variant="body2">
                {me.published ? "Published (guest links live)" : "Not published"}
              </Typography>
            }
          />
        )}

        {isOwner && me.wedding_status !== "archived" && (
          <Button size="small" color="error" disabled={busy} onClick={() => setConfirmDelete(true)}>
            Delete wedding
          </Button>
        )}
      </Stack>

      <Dialog open={confirmDelete} onClose={() => setConfirmDelete(false)}>
        <DialogTitle>Delete this wedding?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Guest links go dark immediately and the dashboard closes. The platform keeps the data
            for 30 days in case you change your mind — after that it&apos;s gone for good.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDelete(false)}>Keep it</Button>
          <Button
            color="error"
            onClick={() => {
              setConfirmDelete(false);
              run(() => adminApi.archiveWedding());
            }}
          >
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
