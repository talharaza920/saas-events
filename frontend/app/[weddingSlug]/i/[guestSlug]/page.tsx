/**
 * Wedding-scoped invite URL: /{weddingSlug}/i/{guestSlug}. The guest slug is
 * globally unique and carries the tenant server-side — the wedding slug here is
 * cosmetic/routing (SAAS_PLAN 1.3), so this route simply reuses the canonical
 * invite page, which resolves everything from the guest slug alone.
 */
export { default, generateMetadata } from "../../../i/[guestSlug]/page";

// Route-segment config can't be re-exported (Next parses it statically).
export const dynamic = "force-dynamic";
