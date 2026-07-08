import type { components } from "@/types/api";

/**
 * Client-side RSVP submission. Runs in the browser, so it uses the public
 * `NEXT_PUBLIC_API_URL` (the server-only `API_BASE` in lib/api.ts isn't readable
 * here). The backend re-validates tier caps + question visibility, so this is a
 * thin transport — the security guarantees live server-side (app/tenancy.py).
 */
export type RsvpConfirmation = components["schemas"]["RsvpConfirmation"];
export type Capabilities = components["schemas"]["Capabilities"];
export type QuestionPublic = components["schemas"]["QuestionPublic"];

/** An answer value as stored/sent — one of these keys depending on question type.
 * (openapi-typescript renders the backend's `dict[str, Any]` JSON column as
 * `Record<string, never>`, which can't hold values, so we override it here.) */
export type AnswerValue = {
  text?: string;
  number?: number;
  choice?: string;
  choices?: string[];
  yesno?: boolean;
};

export type AnswerSubmit = Omit<components["schemas"]["AnswerSubmit"], "value"> & {
  value: AnswerValue;
};
export type AnswerPublic = Omit<components["schemas"]["AnswerPublic"], "value"> & {
  value: AnswerValue;
};
export type CompanionSubmit = Omit<components["schemas"]["CompanionSubmit"], "answers"> & {
  answers?: AnswerSubmit[];
};
export type CompanionPublic = Omit<components["schemas"]["CompanionPublic"], "answers"> & {
  answers: AnswerPublic[];
};
export type RsvpSubmit = Omit<components["schemas"]["RsvpSubmit"], "companions" | "answers"> & {
  companions?: CompanionSubmit[];
  answers?: AnswerSubmit[];
};
export type RsvpPublic = Omit<components["schemas"]["RsvpPublic"], "companions" | "answers"> & {
  companions: CompanionPublic[];
  answers: AnswerPublic[];
};

const CLIENT_API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function submitRsvp(
  guestSlug: string,
  payload: RsvpSubmit,
): Promise<RsvpConfirmation> {
  const res = await fetch(
    `${CLIENT_API_BASE}/api/i/${encodeURIComponent(guestSlug)}/rsvp`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!res.ok) {
    let detail = "Something went wrong saving your RSVP. Please try again.";
    if (res.status === 422) detail = "Please check the form and try again.";
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* keep the friendly default */
    }
    throw new Error(detail);
  }
  return (await res.json()) as RsvpConfirmation;
}
