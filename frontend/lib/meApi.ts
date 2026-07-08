"use client";

import type { components } from "@/types/api";

import { AdminAuthError } from "./adminApi";
import { getToken } from "./adminAuth";

/**
 * Account-level API (no wedding in the path): whoami, the multi-wedding
 * dashboard list, self-serve wedding creation, and co-admin invite acceptance.
 */
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type MeResponse = components["schemas"]["MeResponse"];
export type MyWedding = components["schemas"]["MyWedding"];
export type WeddingCreate = components["schemas"]["WeddingCreate"];
export type WeddingCreated = components["schemas"]["WeddingCreated"];
export type SlugCheck = components["schemas"]["SlugCheck"];
export type InviteAccepted = components["schemas"]["InviteAccepted"];

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getToken();
  if (!token) throw new AdminAuthError("Not signed in");
  const res = await fetch(`${API_BASE}/api${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      Authorization: `Bearer ${token}`,
      ...(init?.headers ?? {}),
    },
  });
  if (res.status === 401 || res.status === 403) {
    let detail: string | undefined;
    try {
      detail = (await res.json())?.detail;
    } catch {
      /* ignore */
    }
    throw new AdminAuthError(detail ?? "Not authorized");
  }
  if (!res.ok) {
    let detail: string | undefined;
    try {
      detail = (await res.json())?.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail ?? `Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

export const meApi = {
  me: () => req<MeResponse>("/me"),
  myWeddings: () => req<MyWedding[]>("/me/weddings"),
  slugCheck: (slug: string) =>
    req<SlugCheck>(`/weddings/slug-check?slug=${encodeURIComponent(slug)}`),
  createWedding: (payload: WeddingCreate) =>
    req<WeddingCreated>("/weddings", { method: "POST", body: JSON.stringify(payload) }),
  acceptInvite: (token: string) =>
    req<InviteAccepted>("/invites/accept", { method: "POST", body: JSON.stringify({ token }) }),
};
