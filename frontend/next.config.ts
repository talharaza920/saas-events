import path from "node:path";
import type { NextConfig } from "next";

// When the backend runs on localhost (local dev), its `/media` images resolve to a
// private IP, which Next 16's image optimizer blocks by default (SSRF guard). In
// production media is served from Supabase (a public host), so the guard stays on
// there — we only relax it when pointed at a local API.
const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const apiIsLocal = /\/\/(localhost|127\.0\.0\.1|\[::1\])/.test(apiUrl);
const isDev = process.env.NODE_ENV !== "production";

// Pin remote images to the EXACT Supabase project host (a `*.supabase.co`
// wildcard would let any Supabase project use us as an image proxy). Derived
// from the Supabase URL env; unset (local dev) simply allow-lists nothing extra.
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const supabaseHost = supabaseUrl ? new URL(supabaseUrl).hostname : "";

// Content-Security-Policy (PRODUCTION ONLY, see headers()). MUI/Emotion needs
// style-src 'unsafe-inline'; Next's hydration runtime needs script-src
// 'unsafe-inline'. connect-src covers the FastAPI backend + Supabase.
const connectSrc = ["'self'", apiUrl, supabaseUrl].filter(Boolean).join(" ");
const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  `img-src 'self' data: blob:${supabaseUrl ? ` ${supabaseUrl}` : ""}${apiIsLocal ? ` ${apiUrl}` : ""}`,
  "font-src 'self' data:",
  `connect-src ${connectSrc}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const nextConfig: NextConfig = {
  // Pin the workspace root to this app. Without it, Next walks up and finds a
  // stray package-lock.json higher up the drive, mis-detecting the monorepo root.
  turbopack: {
    root: path.join(__dirname),
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          // CSP only in production: in dev it fights Next's overlay/HMR and
          // browser devtools/extensions. nosniff/referrer/frame stay on always.
          ...(isDev ? [] : [{ key: "Content-Security-Policy", value: csp }]),
          { key: "X-Content-Type-Options", value: "nosniff" },
          // Guest slugs are credentials — keep them out of referrers.
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
  // Admin-uploaded story images come back as absolute URLs (local FastAPI `/media`
  // in dev, Supabase Storage in prod). next/image rejects remote hosts unless
  // they're allow-listed here. Static `/invite/...` files in public/ are unaffected.
  images: {
    dangerouslyAllowLocalIP: apiIsLocal,
    remotePatterns: [
      { protocol: "http" as const, hostname: "localhost", port: "8000", pathname: "/media/**" },
      ...(supabaseHost
        ? [
            {
              protocol: "https" as const,
              hostname: supabaseHost,
              pathname: "/storage/v1/object/public/**",
            },
          ]
        : []),
    ],
  },
};

export default nextConfig;
