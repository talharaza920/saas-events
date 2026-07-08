"use client";

import { AppRouterCacheProvider } from "@mui/material-nextjs/v16-appRouter";
import CssBaseline from "@mui/material/CssBaseline";
import { ThemeProvider } from "@mui/material/styles";

import { defaultTheme } from "@/theme/buildTheme";

/**
 * App-wide MUI providers. Supplies the DEFAULT "Ever after" theme so the
 * whole app (incl. /admin) is themed out of the box. The guest route
 * (/i/[guestSlug]) nests its own ThemeProvider built from that wedding's stored
 * `theme_tokens`, overriding this default for the invitation subtree only.
 */
export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <AppRouterCacheProvider options={{ key: "mui" }}>
      <ThemeProvider theme={defaultTheme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </AppRouterCacheProvider>
  );
}
