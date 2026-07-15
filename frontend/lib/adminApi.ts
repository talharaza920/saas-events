"use client";

import type { components } from "@/types/api";
import type { ThemeTokensOverride } from "@/theme/types";

import { getToken } from "./adminAuth";

/**
 * Typed client for the wedding-scoped admin API (/api/w/{weddingSlug}/admin/*).
 * Every call attaches the bearer token from {@link getToken}. The backend is the
 * source of truth for authorization (membership rows checked per request) — this
 * layer just transports.
 *
 * The dashboard route sets the active wedding once via {@link setAdminWedding}
 * (from its `[weddingSlug]` route param) before rendering any panel; the module
 * singleton keeps the 17 panel components' imports unchanged. Only one dashboard
 * is ever mounted at a time, so a module-level slug is safe.
 */
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

let _weddingSlug: string | null = null;

/** Set the wedding whose dashboard is being rendered (route param). */
export function setAdminWedding(slug: string): void {
  _weddingSlug = slug;
}

function adminBase(): string {
  if (!_weddingSlug) throw new Error("setAdminWedding() has not been called");
  return `${API_BASE}/api/w/${encodeURIComponent(_weddingSlug)}/admin`;
}

import type { AnswerValue } from "./rsvp";

export type { AnswerValue };

export type AdminMe = components["schemas"]["AdminMe"];
export type GuestCreate = components["schemas"]["GuestCreate"];
export type GuestUpdate = components["schemas"]["GuestUpdate"];
export type QuestionAdmin = components["schemas"]["QuestionAdmin"];
export type QuestionCreate = components["schemas"]["QuestionCreate"];
export type QuestionUpdate = components["schemas"]["QuestionUpdate"];
export type AdminSummary = components["schemas"]["AdminSummary"];
export type QuestionBreakdown = components["schemas"]["QuestionBreakdown"];
export type OptionCount = components["schemas"]["OptionCount"];
export type GroupBreakdown = components["schemas"]["GroupBreakdown"];
export type CapacityConfig = components["schemas"]["CapacityConfig"];
export type PivotSummary = components["schemas"]["PivotSummary"];
export type TimelineSummary = components["schemas"]["TimelineSummary"];
export type TimelinePoint = components["schemas"]["TimelinePoint"];
// openapi-typescript renders the answer `value` JSON column as `Record<string,
// never>`; override it (and the embeds that carry it) with usable answer types.
export type AnswerAdmin = Omit<components["schemas"]["AnswerAdmin"], "value"> & {
  value: AnswerValue;
};
export type CompanionAdmin = Omit<components["schemas"]["CompanionAdmin"], "answers"> & {
  answers: AnswerAdmin[];
};
export type CompanionUpdate = Omit<components["schemas"]["CompanionUpdate"], "answers"> & {
  answers?: { question_id: string; value: AnswerValue }[] | null;
};
export type GuestRsvpUpdate = Omit<
  components["schemas"]["GuestRsvpUpdate"],
  "answers" | "companions"
> & {
  answers?: { question_id: string; value: AnswerValue }[] | null;
  // The whole +1/child party with each person's own answers (attending only). Omit
  // to leave companions untouched; [] clears them.
  companions?:
    | { kind: string; name: string | null; answers: { question_id: string; value: AnswerValue }[] }[]
    | null;
};
export type GuestAdmin = Omit<components["schemas"]["GuestAdmin"], "companions" | "answers"> & {
  companions: CompanionAdmin[];
  answers: AnswerAdmin[];
};
export type ResponseAdmin = Omit<
  components["schemas"]["ResponseAdmin"],
  "companions" | "answers"
> & { companions: CompanionAdmin[]; answers: AnswerAdmin[] };
export type WishAdmin = components["schemas"]["WishAdmin"];
export type BulkResult = components["schemas"]["BulkResult"];
export type ImportResult = components["schemas"]["ImportResult"];
export type LifecycleResult = components["schemas"]["LifecycleResult"];
export type MemberAdmin = components["schemas"]["MemberAdmin"];
export type MemberInvited = components["schemas"]["MemberInvited"];
// openapi-typescript renders `dict[str, Any]` JSON columns as `Record<string,
// never>`, which can't hold real values. Override those fields with a usable
// object type (the backend accepts any JSON).
type Json = Record<string, unknown>;

export type ContentAdmin = components["schemas"]["ContentAdmin"];
export type ContentUpdate = Omit<
  components["schemas"]["ContentUpdate"],
  "event_details" | "content" | "theme_tokens"
> & { event_details?: Json; content?: Json; theme_tokens?: Json | null };
/**
 * A curated look (8.5e). The generated type marks the fields with server-side
 * defaults optional; the API always sends them, and the console always edits
 * them, so they're required here. `tokens` is a theme_tokens patch (the same
 * shape a wedding stores) rather than the generated `Record<string, never>`.
 */
export type ThemePreset = Omit<
  components["schemas"]["ThemePreset"],
  "tokens" | "swatches" | "description" | "enabled"
> & {
  tokens: ThemeTokensOverride;
  swatches: string[];
  description: string;
  enabled: boolean;
};
export type StoryArcAdmin = components["schemas"]["StoryArcAdmin"];
export type StoryArcCreate = Omit<components["schemas"]["StoryArcCreate"], "content"> & {
  content?: Json;
};
export type StoryArcUpdate = Omit<components["schemas"]["StoryArcUpdate"], "content"> & {
  content?: Json;
};

// --- AI wizard (Phase 8.4) ---------------------------------------------------
// JSON columns again render as `Record<string, never>`; override with Json.
export type AiInputRef = components["schemas"]["AiInputRef"];
export type AiVariantAdmin = Omit<components["schemas"]["AiVariantAdmin"], "content"> & {
  content: Json | null;
};
export type AiJobAdmin = Omit<components["schemas"]["AiJobAdmin"], "proposal" | "variants"> & {
  proposal: Json | null;
  variants: AiVariantAdmin[];
};
export type AiApplyResult = components["schemas"]["AiApplyResult"];
export type AiCreditsInfo = components["schemas"]["AiCreditsInfo"];
export type AiStyleOption = components["schemas"]["AiStyleOption"];
export type AiJobKind = "details" | "story_arc" | "glyph" | "guests";
// arc.beat.N / arc.beat.climax = that panel's generated image (8.5b: the
// climax is illustrated like any beat).
export type AiArtifact = "arc.text" | "glyph" | `arc.beat.${number}` | "arc.beat.climax";

/** Flatten an answer value to a display string (any question type). */
export function formatAnswer(v: AnswerValue | null | undefined): string {
  if (!v) return "";
  if (v.text != null) return v.text;
  if (v.number != null) return String(v.number);
  if (v.choice != null) return v.choice;
  if (Array.isArray(v.choices)) return v.choices.join(", ");
  if (typeof v.yesno === "boolean") return v.yesno ? "Yes" : "No";
  return "";
}

/** Thrown on 401/403 so the dashboard can drop back to the sign-in screen. */
export class AdminAuthError extends Error {}

async function detail(res: Response): Promise<string | undefined> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    /* ignore */
  }
  return undefined;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getToken();
  if (!token) throw new AdminAuthError("Not signed in");
  const res = await fetch(`${adminBase()}${path}`, {
    ...init,
    // The admin GETs (guests/summary/…) come back without Cache-Control, so the
    // browser may serve a stale cached copy — which made the table not reflect
    // adds/deletes/imports until a manual reload (a reload revalidates; the
    // in-app refetch reused the cache). `no-store` forces a fresh response.
    cache: "no-store",
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      Authorization: `Bearer ${token}`,
      ...(init?.headers ?? {}),
    },
  });
  if (res.status === 401 || res.status === 403) {
    throw new AdminAuthError((await detail(res)) ?? "Not authorized");
  }
  if (!res.ok) throw new Error((await detail(res)) ?? `Request failed (${res.status})`);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const adminApi = {
  me: () => req<AdminMe>("/me"),

  listGuests: () => req<GuestAdmin[]>("/guests"),
  createGuest: (g: GuestCreate) =>
    req<GuestAdmin>("/guests", { method: "POST", body: JSON.stringify(g) }),
  updateGuest: (id: string, g: GuestUpdate) =>
    req<GuestAdmin>(`/guests/${id}`, { method: "PATCH", body: JSON.stringify(g) }),
  // Owner override of a guest's RSVP (status + the party answers).
  updateGuestRsvp: (id: string, r: GuestRsvpUpdate) =>
    req<GuestAdmin>(`/guests/${id}/rsvp`, { method: "PUT", body: JSON.stringify(r) }),
  deleteGuest: (id: string) => req<void>(`/guests/${id}`, { method: "DELETE" }),
  // Bulk ops over a selection of guests (only status + delete are bulk-editable).
  // Foreign ids are ignored server-side; `count` is the number actually affected.
  bulkSetRsvp: (ids: string[], status: "attending" | "declined" | "invited" | "pending") =>
    req<BulkResult>("/guests/bulk/rsvp", { method: "POST", body: JSON.stringify({ ids, status }) }),
  bulkDeleteGuests: (ids: string[]) =>
    req<BulkResult>("/guests/bulk/delete", { method: "POST", body: JSON.stringify({ ids }) }),

  updateCompanion: (id: string, c: CompanionUpdate) =>
    req<CompanionAdmin>(`/companions/${id}`, { method: "PATCH", body: JSON.stringify(c) }),
  deleteCompanion: (id: string) => req<void>(`/companions/${id}`, { method: "DELETE" }),

  listQuestions: () => req<QuestionAdmin[]>("/questions"),
  createQuestion: (q: QuestionCreate) =>
    req<QuestionAdmin>("/questions", { method: "POST", body: JSON.stringify(q) }),
  updateQuestion: (id: string, q: QuestionUpdate) =>
    req<QuestionAdmin>(`/questions/${id}`, { method: "PATCH", body: JSON.stringify(q) }),
  deleteQuestion: (id: string) => req<void>(`/questions/${id}`, { method: "DELETE" }),

  listResponses: () => req<ResponseAdmin[]>("/responses"),
  summary: () => req<AdminSummary>("/summary"),
  // Cumulative RSVP timeline — lazy-loaded by the Overview's Trends panel on open.
  summaryTimeline: () => req<TimelineSummary>("/summary/timeline"),
  // Configurable Overview pivot — grouped by `by`, stacked by `then`, optionally
  // scoped to a `side` and/or `status`. Re-fetched when the owner changes a control.
  summaryPivot: (by: string, then?: string | null, opts?: { side?: string; status?: string }) => {
    const p = new URLSearchParams({ by, then: then ?? "" });
    if (opts?.side) p.set("side", opts.side);
    if (opts?.status) p.set("status", opts.status);
    return req<PivotSummary>(`/summary/pivot?${p.toString()}`);
  },

  listWishes: () => req<WishAdmin[]>("/wishes"),
  moderateWish: (id: string, approved: boolean) =>
    req<WishAdmin>(`/wishes/${id}`, { method: "PATCH", body: JSON.stringify({ approved }) }),
  deleteWish: (id: string) => req<void>(`/wishes/${id}`, { method: "DELETE" }),

  getContent: () => req<ContentAdmin>("/content"),
  updateContent: (c: ContentUpdate) =>
    req<ContentAdmin>("/content", { method: "PATCH", body: JSON.stringify(c) }),

  // Theme presets (8.5e). The catalogue is platform-owned; applying one COPIES
  // its tokens onto the wedding (server-side, by id — the client never sends the
  // tokens it was shown), and every token stays editable afterwards.
  themePresets: () => req<ThemePreset[]>("/theme/presets"),
  applyThemePreset: (presetId: string) =>
    req<ContentAdmin>("/theme/preset", {
      method: "POST",
      body: JSON.stringify({ preset_id: presetId }),
    }),

  listArcs: () => req<StoryArcAdmin[]>("/story-arcs"),
  createArc: (a: StoryArcCreate) =>
    req<StoryArcAdmin>("/story-arcs", { method: "POST", body: JSON.stringify(a) }),
  updateArc: (id: string, a: StoryArcUpdate) =>
    req<StoryArcAdmin>(`/story-arcs/${id}`, { method: "PATCH", body: JSON.stringify(a) }),
  deleteArc: (id: string) => req<void>(`/story-arcs/${id}`, { method: "DELETE" }),

  uploadImage: (file: File) => uploadImage(file),

  importGuests: (file: File, commit: boolean) => importGuests(file, commit),

  // --- Wedding lifecycle (Phase 2) ---------------------------------------
  submitApproval: () => req<LifecycleResult>("/submit-approval", { method: "POST" }),
  setPublished: (published: boolean) =>
    req<LifecycleResult>("/publish", { method: "POST", body: JSON.stringify({ published }) }),
  updateWeddingSettings: (s: {
    admins_can_publish?: boolean;
    phone_region?: string;
    setup_dismissed?: boolean;
  }) =>
    req<Record<string, unknown>>("/settings", { method: "PATCH", body: JSON.stringify(s) }),
  archiveWedding: () => req<LifecycleResult>("", { method: "DELETE" }),

  // --- Members (Phase 3) --------------------------------------------------
  listMembers: () => req<MemberAdmin[]>("/members"),
  inviteMember: (email: string, role: "owner" | "admin" = "admin") =>
    req<MemberInvited>("/members", { method: "POST", body: JSON.stringify({ email, role }) }),
  updateMemberRole: (id: string, role: "owner" | "admin") =>
    req<MemberAdmin>(`/members/${id}`, { method: "PATCH", body: JSON.stringify({ role }) }),
  revokeMember: (id: string) => req<MemberAdmin>(`/members/${id}`, { method: "DELETE" }),
  transferOwnership: (id: string) =>
    req<MemberAdmin>(`/members/${id}/transfer-ownership`, { method: "POST" }),
};

/**
 * The AI wizard API (/admin/ai/*, Phase 8.4). Same transport + wedding binding
 * as {@link adminApi}. The model proposes; code disposes — nothing here writes
 * wedding content except apply, which is allowlisted server-side.
 */
export const aiApi = {
  createInput: (text: string) =>
    req<AiInputRef>("/ai/inputs", { method: "POST", body: JSON.stringify({ kind: "text", text }) }),
  // A media submission (voice note / photo / PDF) — multipart, like uploadImage.
  uploadInput: (file: File, opts?: { role?: "source" | "reference"; consent?: boolean }) =>
    uploadAiInput(file, opts),
  // The Idempotency-Key makes a double-click return the same job instead of a 409.
  createJob: (kind: AiJobKind, inputIds: string[], options: Json = {}, idempotencyKey?: string) =>
    req<AiJobAdmin>("/ai/jobs", {
      method: "POST",
      body: JSON.stringify({ kind, input_ids: inputIds, options }),
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
    }),
  listJobs: () => req<AiJobAdmin[]>("/ai/jobs"),
  getJob: (id: string) => req<AiJobAdmin>(`/ai/jobs/${id}`),
  // Drives exactly ONE pipeline step; `expectedStep` makes retries replay-safe.
  advanceJob: (id: string, expectedStep?: number) =>
    req<AiJobAdmin>(`/ai/jobs/${id}/advance`, {
      method: "POST",
      body: JSON.stringify({ expected_step: expectedStep ?? null }),
    }),
  // The couple's own edits to a story draft, and the illustration style —
  // free, no provider call (8.5b). Omitted fields are left alone.
  editProposal: (
    id: string,
    patch: { story_arc?: Json; style_preset?: string; style_note?: string },
  ) =>
    req<AiJobAdmin>(`/ai/jobs/${id}/proposal`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  // Renders panels of a settled draft — 1 credit each. `targets` omitted =
  // the next batch of un-illustrated ones ("illustrate the rest").
  illustrate: (id: string, targets?: string[]) =>
    req<AiJobAdmin>(`/ai/jobs/${id}/illustrate`, {
      method: "POST",
      body: JSON.stringify({ targets: targets ?? null }),
    }),
  styles: () => req<AiStyleOption[]>("/ai/styles"),
  // 8.5d: the consented photos this run should draw the couple from. A SET —
  // posting [] detaches and deletes them, which is how they change their mind.
  setReferences: (id: string, inputIds: string[]) =>
    req<AiJobAdmin>(`/ai/jobs/${id}/references`, {
      method: "POST",
      body: JSON.stringify({ input_ids: inputIds }),
    }),
  // 8.5c: answer a guest run's open questions. Free, and it buys exactly ONE
  // more extraction round — the server enforces both.
  answerQuestions: (id: string, answers: { index: number; answer: string }[]) =>
    req<AiJobAdmin>(`/ai/jobs/${id}/answers`, {
      method: "POST",
      body: JSON.stringify({ answers }),
    }),
  regenerate: (id: string, artifact: AiArtifact, steer?: string) =>
    req<AiVariantAdmin>(`/ai/jobs/${id}/regenerate`, {
      method: "POST",
      body: JSON.stringify({ artifact, steer: steer?.trim() || null }),
    }),
  selectVariant: (id: string, artifact: AiArtifact, variantId: string) =>
    req<AiJobAdmin>(`/ai/jobs/${id}/select`, {
      method: "POST",
      body: JSON.stringify({ artifact, variant_id: variantId }),
    }),
  applyJob: (id: string, selections?: string[]) =>
    req<AiApplyResult>(`/ai/jobs/${id}/apply`, {
      method: "POST",
      body: JSON.stringify({ selections: selections ?? null }),
    }),
  cancelJob: (id: string) => req<AiJobAdmin>(`/ai/jobs/${id}/cancel`, { method: "POST" }),
  credits: () => req<AiCreditsInfo>("/ai/credits"),
};

/** Upload a guest spreadsheet (CSV/XLSX). `commit=false` is a dry-run preview. */
async function importGuests(file: File, commit: boolean): Promise<ImportResult> {
  const token = await getToken();
  if (!token) throw new AdminAuthError("Not signed in");
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${adminBase()}/import?commit=${commit ? 1 : 0}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (res.status === 401 || res.status === 403) {
    throw new AdminAuthError((await detail(res)) ?? "Not authorized");
  }
  if (!res.ok) throw new Error((await detail(res)) ?? `Import failed (${res.status})`);
  return (await res.json()) as ImportResult;
}

/**
 * Upload an image via multipart/form-data. Can't use {@link req} — the browser
 * must set the multipart Content-Type (with boundary) itself, so we only attach
 * the Authorization header. Returns the stored public URL.
 */
async function uploadImage(file: File): Promise<string> {
  const token = await getToken();
  if (!token) throw new AdminAuthError("Not signed in");
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${adminBase()}/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (res.status === 401 || res.status === 403) {
    throw new AdminAuthError((await detail(res)) ?? "Not authorized");
  }
  if (!res.ok) throw new Error((await detail(res)) ?? `Upload failed (${res.status})`);
  return ((await res.json()) as { url: string }).url;
}

/**
 * Upload one AI-wizard media submission (audio/image/PDF, max 10 MB).
 *
 * `role: "reference"` is a photo OF THE COUPLE (8.5d) and requires `consent` —
 * the server records who ticked the box and when, and refuses the upload
 * without it. Consent travels WITH the file, on the request that carries it;
 * there is no "consent later" and no way to consent on someone's behalf.
 */
async function uploadAiInput(
  file: File,
  opts: { role?: "source" | "reference"; consent?: boolean } = {},
): Promise<AiInputRef> {
  const token = await getToken();
  if (!token) throw new AdminAuthError("Not signed in");
  const form = new FormData();
  form.append("file", file);
  if (opts.role) form.append("role", opts.role);
  if (opts.consent) form.append("consent", "true");
  const res = await fetch(`${adminBase()}/ai/inputs/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (res.status === 401 || res.status === 403) {
    throw new AdminAuthError((await detail(res)) ?? "Not authorized");
  }
  if (!res.ok) throw new Error((await detail(res)) ?? `Upload failed (${res.status})`);
  return (await res.json()) as AiInputRef;
}

/** Download an authed file (needs the bearer header, so fetch → blob → click). */
async function downloadAuthed(path: string, filename: string): Promise<void> {
  const token = await getToken();
  if (!token) throw new AdminAuthError("Not signed in");
  const res = await fetch(`${adminBase()}/${path}`, {
    cache: "no-store",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Download the guest XLSX. */
export const downloadXlsx = (filename = "guests.xlsx") => downloadAuthed("export.xlsx", filename);
/** Download the fillable import template (XLSX). */
export const downloadTemplate = (filename = "guest-template.xlsx") =>
  downloadAuthed("template.xlsx", filename);

/** Absolute URL for a guest invite link (for copy-to-clipboard in the UI). */
export function inviteUrl(invitePath: string): string {
  if (typeof window === "undefined") return invitePath;
  return window.location.origin + invitePath;
}
