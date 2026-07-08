import { createTheme, type Theme } from "@mui/material/styles";

import { defaultThemeConfig } from "./defaultThemeConfig";
import type { ThemeTokens, ThemeTokensOverride } from "./types";

/**
 * Expose the full resolved token set on the theme as `theme.extra` so components
 * can read brand tokens that don't map onto MUI's stock palette (paperAlt,
 * inkSoft, primaryDeep, dream wash, story/logo fonts, soft/pop shadows, radiusLg)
 * via `sx={{ ... (t) => t.extra.colors.paperAlt }}` — never a raw hex/px.
 */
declare module "@mui/material/styles" {
  interface Theme {
    extra: ThemeTokens;
  }
  interface ThemeOptions {
    extra?: ThemeTokens;
  }
}

/** Deep-merge a per-wedding override onto the default token template. */
export function resolveTokens(override?: ThemeTokensOverride | null): ThemeTokens {
  if (!override) return defaultThemeConfig;
  return {
    colors: { ...defaultThemeConfig.colors, ...(override.colors ?? {}) },
    typography: { ...defaultThemeConfig.typography, ...(override.typography ?? {}) },
    shadows: { ...defaultThemeConfig.shadows, ...(override.shadows ?? {}) },
    radius: override.radius ?? defaultThemeConfig.radius,
    radiusLg: override.radiusLg ?? defaultThemeConfig.radiusLg,
    spacingUnit: override.spacingUnit ?? defaultThemeConfig.spacingUnit,
    storyFeather: override.storyFeather ?? defaultThemeConfig.storyFeather,
  };
}

/**
 * Build an MUI theme from resolved tokens. The guest site and admin pass the
 * wedding's stored `theme_tokens` here; with no override it renders the default
 * "Ever after" template. Components reference palette/typography tokens
 * (e.g. `sx={{ color: 'primary.main' }}`) or `theme.extra.*` — never raw values.
 */
export function buildTheme(override?: ThemeTokensOverride | null): Theme {
  const t = resolveTokens(override);
  return createTheme({
    extra: t,
    palette: {
      mode: "light",
      background: { default: t.colors.paper, paper: t.colors.paperAlt },
      text: { primary: t.colors.ink, secondary: t.colors.inkSoft },
      primary: { main: t.colors.primary, dark: t.colors.primaryDeep, contrastText: "#fff" },
      secondary: { main: t.colors.secondary, contrastText: t.colors.paper },
      success: { main: t.colors.yes },
      error: { main: t.colors.no },
      warning: { main: t.colors.amber },
      divider: t.colors.paperEdge,
    },
    typography: {
      fontFamily: t.typography.body,
      h1: { fontFamily: t.typography.display, fontWeight: 800, letterSpacing: "-0.02em" },
      h2: { fontFamily: t.typography.display, fontWeight: 700, letterSpacing: "-0.01em" },
      h3: { fontFamily: t.typography.display, fontWeight: 700 },
      h4: { fontFamily: t.typography.display, fontWeight: 600 },
      // `subtitle1` is reserved for the storybook narrator voice.
      subtitle1: { fontFamily: t.typography.story, fontStyle: "italic" },
      button: { textTransform: "none", fontWeight: 700 },
    },
    shape: { borderRadius: t.radius },
    spacing: t.spacingUnit,
  });
}

/** Convenience: the default template theme. */
export const defaultTheme = buildTheme();
