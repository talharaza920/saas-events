"use client";

import type { components } from "@/types/api";

import { getToken } from "./adminAuth";

/**
 * Typed client for the owner-authenticated admin API (/api/admin/*). Every call
 * attaches the bearer token from {@link getToken}. The backend is the source of
 * truth for authorization (verifies the JWT + email allowlist) — this layer just
 * transports.
 */
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
// openapi-typescript renders `dict[str, Any]` JSON columns as `Record<string,
// never>`, which can't hold real values. Override those fields with a usable
// object type (the backend accepts any JSON).
type Json = Record<string, unknown>;

export type ContentAdmin = components["schemas"]["ContentAdmin"];
export type ContentUpdate = Omit<
  components["schemas"]["ContentUpdate"],
  "event_details" | "content" | "theme_tokens"
> & { event_details?: Json; content?: Json; theme_tokens?: Json | null };
export type StoryArcAdmin = components["schemas"]["StoryArcAdmin"];
export type StoryArcCreate = Omit<components["schemas"]["StoryArcCreate"], "content"> & {
  content?: Json;
};
export type StoryArcUpdate = Omit<components["schemas"]["StoryArcUpdate"], "content"> & {
  content?: Json;
};

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
  const res = await fetch(`${API_BASE}/api/admin${path}`, {
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

  listArcs: () => req<StoryArcAdmin[]>("/story-arcs"),
  createArc: (a: StoryArcCreate) =>
    req<StoryArcAdmin>("/story-arcs", { method: "POST", body: JSON.stringify(a) }),
  updateArc: (id: string, a: StoryArcUpdate) =>
    req<StoryArcAdmin>(`/story-arcs/${id}`, { method: "PATCH", body: JSON.stringify(a) }),
  deleteArc: (id: string) => req<void>(`/story-arcs/${id}`, { method: "DELETE" }),

  uploadImage: (file: File) => uploadImage(file),

  importGuests: (file: File, commit: boolean) => importGuests(file, commit),
};

/** Upload a guest spreadsheet (CSV/XLSX). `commit=false` is a dry-run preview. */
async function importGuests(file: File, commit: boolean): Promise<ImportResult> {
  const token = await getToken();
  if (!token) throw new AdminAuthError("Not signed in");
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/admin/import?commit=${commit ? 1 : 0}`, {
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
  const res = await fetch(`${API_BASE}/api/admin/upload`, {
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

/** Download an authed file (needs the bearer header, so fetch → blob → click). */
async function downloadAuthed(path: string, filename: string): Promise<void> {
  const token = await getToken();
  if (!token) throw new AdminAuthError("Not signed in");
  const res = await fetch(`${API_BASE}/api/admin/${path}`, {
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
