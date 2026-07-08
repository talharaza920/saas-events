"use client";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

/**
 * Owner (admin) auth for the /admin dashboard. Two modes, mirroring the backend
 * (app/auth.py):
 *
 *   • Local dev — `NEXT_PUBLIC_DEV_ADMIN_TOKEN` is set (in .env.local) and used
 *     directly as the bearer token. No Supabase, no Google login. Matches the
 *     backend's `dev_admin_token`. NEVER set this in production.
 *   • Production — Supabase Google sign-in. The session's `access_token` (a
 *     Supabase-signed JWT) is the bearer; the backend verifies it + the email
 *     allowlist.
 *
 * Guests never authenticate — this is the only login in the app.
 */
const DEV_TOKEN = process.env.NEXT_PUBLIC_DEV_ADMIN_TOKEN ?? "";
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
// Supabase's newer "publishable" key (sb_publishable_…) or the legacy anon key.
const SUPABASE_KEY =
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ??
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ??
  "";

export const isDevAuth = Boolean(DEV_TOKEN);
export const isSupabaseConfigured = Boolean(SUPABASE_URL && SUPABASE_KEY);

let _client: SupabaseClient | null = null;

export function supabase(): SupabaseClient {
  if (!isSupabaseConfigured) {
    throw new Error("Supabase is not configured (set NEXT_PUBLIC_SUPABASE_URL / _ANON_KEY).");
  }
  if (!_client) _client = createClient(SUPABASE_URL, SUPABASE_KEY);
  return _client;
}

/** The bearer token for admin API calls, or null if not signed in. */
export async function getToken(): Promise<string | null> {
  if (isDevAuth) return DEV_TOKEN;
  if (!isSupabaseConfigured) return null;
  const { data } = await supabase().auth.getSession();
  return data.session?.access_token ?? null;
}

export async function signInWithGoogle(): Promise<void> {
  await supabase().auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: window.location.origin + "/admin" },
  });
}

export async function signOut(): Promise<void> {
  if (isSupabaseConfigured) await supabase().auth.signOut();
}
