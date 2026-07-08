"use client";

import MenuIcon from "@mui/icons-material/Menu";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import { useEffect, useState } from "react";

import type { NavContent } from "@/lib/content";

import MascotBadge from "./brand/MascotBadge";

/**
 * Fixed top nav — transparent over the hero, frosted/solid once scrolled. Brand
 * + anchor links + RSVP CTA all come from the wedding's `content.nav`. On small
 * screens the anchor links collapse, leaving brand + RSVP.
 */
export default function Nav({ nav }: { nav: NavContent }) {
  const [solid, setSolid] = useState(false);
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);

  useEffect(() => {
    const onScroll = () => setSolid(window.scrollY > 60);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <Box
      component="nav"
      sx={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: (t) => t.zIndex.appBar,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        px: { xs: 2, sm: 5 },
        py: solid ? 1.25 : 1.75,
        transition: "background .3s ease, box-shadow .3s ease, padding .3s ease",
        ...(solid
          ? {
              bgcolor: (t) => `${t.extra.colors.paper}DB`,
              backdropFilter: "blur(10px)",
              boxShadow: (t) => `0 1px 0 ${t.extra.colors.paperEdge}`,
            }
          : {}),
      }}
    >
      <Box component="a" href="#cover" sx={{ display: "flex", alignItems: "center", gap: 1.5, textDecoration: "none", color: "text.primary" }}>
        <MascotBadge size={38} mood="peek" />
        {nav.brand && (
          <Box component="span" sx={{ fontFamily: (t) => t.extra.typography.logo, fontWeight: 700, fontSize: "1.05rem" }}>
            {nav.brand}
          </Box>
        )}
      </Box>

      <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
        {nav.links.map((l) => (
          <Box
            key={l.href}
            component="a"
            href={l.href}
            sx={{
              display: { xs: "none", md: "inline-flex" },
              fontSize: 14,
              fontWeight: 600,
              textDecoration: "none",
              color: "text.secondary",
              px: 1.75,
              py: 1,
              borderRadius: 999,
              transition: "color .2s, background .2s",
              "&:hover": { color: "text.primary", bgcolor: "background.paper" },
            }}
          >
            {l.label}
          </Box>
        ))}
        {nav.cta && (
          <Button href="#rsvp" variant="contained" color="primary" sx={{ borderRadius: 999, px: 2.5, ml: 0.5 }}>
            {nav.cta}
          </Button>
        )}

        {/* Mobile menu — shows only where the inline links are hidden (< md). */}
        {nav.links.length > 0 && (
          <>
            <IconButton
              aria-label="Open menu"
              aria-haspopup="true"
              onClick={(e) => setMenuAnchor(e.currentTarget)}
              sx={{ display: { xs: "inline-flex", md: "none" }, ml: 0.5, color: "text.primary" }}
            >
              <MenuIcon />
            </IconButton>
            <Menu
              anchorEl={menuAnchor}
              open={Boolean(menuAnchor)}
              onClose={() => setMenuAnchor(null)}
              anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
              transformOrigin={{ vertical: "top", horizontal: "right" }}
              slotProps={{ paper: { sx: { borderRadius: 2, mt: 1, minWidth: 180 } } }}
            >
              {nav.links.map((l) => (
                <MenuItem
                  key={l.href}
                  component="a"
                  href={l.href}
                  onClick={() => setMenuAnchor(null)}
                  sx={{ fontWeight: 600, fontSize: 15, py: 1.25 }}
                >
                  {l.label}
                </MenuItem>
              ))}
            </Menu>
          </>
        )}
      </Stack>
    </Box>
  );
}
