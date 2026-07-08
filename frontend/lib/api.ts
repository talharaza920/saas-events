import type { components } from "@/types/api";

/**
 * Server-side API client for the FastAPI backend. The invite is fetched during
 * SSR; prefer a server-only `API_BASE` (e.g. an internal URL on Vercel), falling
 * back to the public `NEXT_PUBLIC_API_URL` used elsewhere, then local dev.
 */
const API_BASE =
  process.env.API_BASE ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type InviteResponse = components["schemas"]["InviteResponse"];
export type WeddingPublic = components["schemas"]["WeddingPublic"];
export type GuestPublic = components["schemas"]["GuestPublic"];
export type Capabilities = components["schemas"]["Capabilities"];
export type QuestionPublic = components["schemas"]["QuestionPublic"];
export type RsvpPublic = components["schemas"]["RsvpPublic"];
export type RsvpSubmit = components["schemas"]["RsvpSubmit"];
export type WishPublic = components["schemas"]["WishPublic"];
export type LandingResponse = components["schemas"]["LandingResponse"];

/** A 404 from the invite endpoint (unknown / inactive link). */
export class InviteNotFound extends Error {}

/**
 * Fetch the public "no link" landing copy for the site root. Returns null on any
 * failure (backend down, no wedding seeded) so the root page falls back to its
 * built-in defaults rather than erroring.
 */
export async function fetchLanding(): Promise<LandingResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/api/landing`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as LandingResponse;
  } catch {
    return null;
  }
}

/**
 * Fetch the invitation payload for a guest slug. Throws {@link InviteNotFound}
 * on 404 so the route can render its not-found UI. No caching — RSVP state and
 * content must be fresh per request.
 */
export async function fetchInvite(guestSlug: string): Promise<InviteResponse> {
  const res = await fetch(`${API_BASE}/api/i/${encodeURIComponent(guestSlug)}`, {
    cache: "no-store",
  });
  if (res.status === 404) throw new InviteNotFound();
  if (!res.ok) throw new Error(`Invite fetch failed: ${res.status}`);
  return (await res.json()) as InviteResponse;
}

/**
 * Fetch the approved guestbook wall for a guest slug (SSR initial render). A
 * failure degrades to an empty wall rather than breaking the whole invite — the
 * guestbook is non-critical chrome.
 */
export async function fetchWishes(guestSlug: string): Promise<WishPublic[]> {
  try {
    const res = await fetch(`${API_BASE}/api/i/${encodeURIComponent(guestSlug)}/wishes`, {
      cache: "no-store",
    });
    if (!res.ok) return [];
    return (await res.json()) as WishPublic[];
  } catch {
    return [];
  }
}
