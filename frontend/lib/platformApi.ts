"use client";

import type { components } from "@/types/api";

import { AdminAuthError } from "./adminApi";
import { getToken } from "./adminAuth";

/**
 * Platform (super admin) console API — /api/platform/*. The backend gates every
 * call with require_platform_admin; a 403 here means "not a platform admin".
 */
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type PlatformWedding = components["schemas"]["PlatformWedding"];
export type ApprovalItem = components["schemas"]["ApprovalItem"];
export type PlatformSettingsPayload = components["schemas"]["PlatformSettingsPayload"];
export type PlatformUser = components["schemas"]["PlatformUser"];
export type PlatformStats = components["schemas"]["PlatformStats"];
export type AuditEntry = components["schemas"]["AuditEntry"];
export type PlanAdmin = components["schemas"]["PlanAdmin"];
export type WeddingPlanAdmin = components["schemas"]["WeddingPlanAdmin"];
// --- AI console (Phase 8.4) --------------------------------------------------
export type AiSettingsPayload = components["schemas"]["AiSettingsPayload"];
export type AiPromptAdmin = components["schemas"]["AiPromptAdmin"];
export type AiPromptSave = components["schemas"]["AiPromptSave"];
export type AiUsageSummary = components["schemas"]["AiUsageSummary"];
export type AiUsageDay = components["schemas"]["AiUsageDay"];
export type AiUsageTopWedding = components["schemas"]["AiUsageTopWedding"];

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getToken();
  if (!token) throw new AdminAuthError("Not signed in");
  const res = await fetch(`${API_BASE}/api/platform${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      Authorization: `Bearer ${token}`,
      ...(init?.headers ?? {}),
    },
  });
  if (res.status === 401 || res.status === 403) {
    throw new AdminAuthError("Platform admin access required");
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

export const platformApi = {
  weddings: (status?: string) =>
    req<PlatformWedding[]>(`/weddings${status ? `?status=${encodeURIComponent(status)}` : ""}`),
  approve: (id: string) =>
    req<PlatformWedding>(`/weddings/${id}/approve`, { method: "POST", body: JSON.stringify({}) }),
  deny: (id: string, reason: string) =>
    req<PlatformWedding>(`/weddings/${id}/deny`, { method: "POST", body: JSON.stringify({ reason }) }),
  suspend: (id: string, reason?: string) =>
    req<PlatformWedding>(`/weddings/${id}/suspend`, {
      method: "POST",
      body: JSON.stringify({ reason: reason ?? null }),
    }),
  reinstate: (id: string) => req<PlatformWedding>(`/weddings/${id}/reinstate`, { method: "POST" }),

  approvals: () => req<ApprovalItem[]>("/approvals"),

  getApprovalSettings: () => req<PlatformSettingsPayload>("/settings/approval"),
  putApprovalSettings: (s: PlatformSettingsPayload) =>
    req<PlatformSettingsPayload>("/settings/approval", { method: "PUT", body: JSON.stringify(s) }),

  users: () => req<PlatformUser[]>("/users"),
  setUserDisabled: (userId: string, disabled: boolean) =>
    req<PlatformUser>(`/users/${encodeURIComponent(userId)}/disable`, {
      method: "POST",
      body: JSON.stringify({ disabled }),
    }),

  stats: () => req<PlatformStats>("/stats"),
  audit: (limit = 50) => req<AuditEntry[]>(`/audit?limit=${limit}`),

  plans: () => req<PlanAdmin[]>("/plans"),
  createPlan: (p: { name: string; description?: string; is_default?: boolean; entitlements: Record<string, unknown> }) =>
    req<PlanAdmin>("/plans", { method: "POST", body: JSON.stringify(p) }),
  updatePlan: (id: string, p: Partial<{ name: string; description: string; is_default: boolean; entitlements: Record<string, unknown>; archived: boolean }>) =>
    req<PlanAdmin>(`/plans/${id}`, { method: "PATCH", body: JSON.stringify(p) }),
  assignPlan: (weddingId: string, planId: string | null, overrides?: Record<string, unknown> | null) =>
    req<WeddingPlanAdmin>(`/weddings/${weddingId}/plan`, {
      method: "PUT",
      body: JSON.stringify({ plan_id: planId, overrides: overrides ?? null }),
    }),

  // --- AI console (Phase 8.4): circuit breaker, prompt registry, spend -----
  getAiSettings: () => req<AiSettingsPayload>("/settings/ai"),
  putAiSettings: (s: AiSettingsPayload) =>
    req<AiSettingsPayload>("/settings/ai", { method: "PUT", body: JSON.stringify(s) }),
  aiPrompts: () => req<AiPromptAdmin[]>("/ai/prompts"),
  // Saves a NEW version (never edits in place); rollback = deactivate below.
  saveAiPrompt: (key: string, body: AiPromptSave) =>
    req<AiPromptAdmin>(`/ai/prompts/${encodeURIComponent(key)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  activateAiPrompt: (key: string, provider: string, version: number, active: boolean) =>
    req<AiPromptAdmin>(`/ai/prompts/${encodeURIComponent(key)}/activate`, {
      method: "POST",
      body: JSON.stringify({ provider, version, active }),
    }),
  aiUsage: () => req<AiUsageSummary>("/ai/usage"),
};
