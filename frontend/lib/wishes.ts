import type { components } from "@/types/api";

/**
 * Client-side guestbook calls. Like lib/rsvp.ts, these run in the browser and use
 * the public `NEXT_PUBLIC_API_URL`. The slug gates access + scopes the tenant
 * server-side; this is a thin transport.
 */
export type WishPublic = components["schemas"]["WishPublic"];
export type WishCreate = components["schemas"]["WishCreate"];
export type WishCreated = components["schemas"]["WishCreated"];

const CLIENT_API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function submitWish(
  guestSlug: string,
  payload: WishCreate,
): Promise<WishCreated> {
  const res = await fetch(
    `${CLIENT_API_BASE}/api/i/${encodeURIComponent(guestSlug)}/wishes`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!res.ok) {
    let detail = "Could not post your message. Please try again.";
    if (res.status === 422) detail = "Please write a short message first.";
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* keep the friendly default */
    }
    throw new Error(detail);
  }
  return (await res.json()) as WishCreated;
}

/** Re-fetch the wall after posting (client side). */
export async function fetchWishes(guestSlug: string): Promise<WishPublic[]> {
  const res = await fetch(
    `${CLIENT_API_BASE}/api/i/${encodeURIComponent(guestSlug)}/wishes`,
    { cache: "no-store" },
  );
  if (!res.ok) return [];
  return (await res.json()) as WishPublic[];
}
