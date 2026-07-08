"use client";

import { ThemeProvider } from "@mui/material/styles";
import { useMemo } from "react";

import { buildTheme } from "@/theme/buildTheme";
import type { ThemeTokensOverride } from "@/theme/types";

/**
 * Wraps the invitation subtree in the wedding's OWN theme, built from its stored
 * `theme_tokens` (a partial override deep-merged onto the default "Ever after"
 * template). This nests inside the app-wide default ThemeProvider, so a future
 * second wedding renders with its own palette without touching components.
 */
export default function InviteThemeProvider({
  tokens,
  children,
}: {
  tokens: ThemeTokensOverride | null;
  children: React.ReactNode;
}) {
  const theme = useMemo(() => buildTheme(tokens), [tokens]);
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}
