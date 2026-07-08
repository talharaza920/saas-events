import type { ThemeTokens } from "./types";

/**
 * "Ever after" — the DEFAULT theme template.
 *
 * Tokens are derived from a hand-drawn comic-style palette (see docs/DESIGN.md):
 * cream paper, ink line art, soft anime sunset accents. This object is also the
 * seed for a new wedding's `theme_tokens` in the DB. Every value lives here —
 * never hardcode a hex/px/font in a component.
 *
 * Font families assume the matching @fontsource / next/font faces are loaded in
 * the app layout. Swapping a face = editing this file (or a wedding override).
 */
export const defaultThemeConfig: ThemeTokens = {
  colors: {
    paper: "#F3EEE3",
    paperAlt: "#ECE4D4",
    paperEdge: "#E3D9C5",
    ink: "#1A1714",
    inkSoft: "#5B534A",
    primary: "#D98C6A",
    primaryDeep: "#B5704F",
    secondary: "#8E9BB3",
    accentSage: "#9DAE8E",
    accentLav: "#C9BBD6",
    yes: "#6FA38A",
    no: "#B0796E",
    amber: "#CDA15B",
    dream1: "#CDBFE0",
    dream2: "#F3C9C0",
    dream3: "#CFE0D6",
    dream4: "#F6E3B8",
  },
  // Reference the CSS variables set by next/font in app/layout.tsx, with
  // robust fallbacks. Keeps the theme decoupled from next/font hashed names.
  typography: {
    logo: 'var(--font-display), "Baloo 2", system-ui, sans-serif',
    display: 'var(--font-display), "Baloo 2", system-ui, sans-serif',
    story: 'var(--font-story), "Lora", Georgia, serif',
    body: 'var(--font-body), "Plus Jakarta Sans", system-ui, -apple-system, sans-serif',
  },
  shadows: {
    soft: "0 1px 2px rgba(26,23,20,.04), 0 8px 28px -12px rgba(26,23,20,.18)",
    pop: "0 2px 4px rgba(26,23,20,.05), 0 18px 48px -16px rgba(26,23,20,.28)",
  },
  radius: 14,
  radiusLg: 22,
  spacingUnit: 8,
  // Subtle edge feather on story panels — softens the outermost ~4% of each
  // image edge so it melts into the cream page. Raise for a dreamier dissolve.
  storyFeather: 4,
};
