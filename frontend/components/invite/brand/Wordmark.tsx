"use client";

import Box from "@mui/material/Box";
import { keyframes } from "@mui/system";
import { useId } from "react";

import type { BrandIconMode } from "@/lib/content";

import CatGlyph from "./CatGlyph";

const spinKf = keyframes`to { transform: rotate(360deg); }`;

/** What sits in the still center of the spinning ring. */
export interface WordmarkIcon {
  mode: BrandIconMode;
  /** Uploaded square image URL — used only when mode === "custom". */
  url?: string;
  /** AI-designed SVG children (100×100 viewBox, server-sanitised) — used only
   * when mode === "svg". */
  svg?: string;
}

/**
 * Circular rotating wordmark — the brand line set on a ring (top + bottom arcs)
 * around a center icon, exactly like the comic's panel 00. Both the ring text
 * and the icon are owner-configurable (data on the wedding, see `content.brand`);
 * the text and icon default to the original cat mark when nothing is stored.
 * Respects prefers-reduced-motion. The ring text uses the logo font token.
 */
export default function Wordmark({
  size = 220,
  spin = true,
  speed = 26,
  text = "Ever after",
  icon = { mode: "default" },
}: {
  size?: number;
  spin?: boolean;
  speed?: number;
  text?: string;
  icon?: WordmarkIcon;
}) {
  const id = useId().replace(/:/g, "");
  return (
    <Box sx={{ position: "relative", display: "grid", placeItems: "center", width: size, height: size }}>
      <Box
        component="svg"
        viewBox="0 0 200 200"
        width={size}
        height={size}
        sx={{
          animation: spin ? `${spinKf} ${speed}s linear infinite` : "none",
          "@media (prefers-reduced-motion: reduce)": { animation: "none" },
        }}
      >
        {/* CONTINUOUS ring, readable-at-BOTTOM. Both bands flow the same rotational
            direction (text sits on the INSIDE of the circle) so the full-circle spin
            reads as one coherent rotating band — and the orientation is chosen so a
            line is right-side-up when it's at the BOTTOM and flipped when it's at the
            TOP. So at rest the bottom line reads correctly and the top line is
            inverted; as it spins, whatever text is at the bottom is always upright.

            Both arcs run right→left over the top / left→right under the bottom, both
            at radius r=76. We can't rely on `dominant-baseline:central` to vertically
            centre the text — Chrome honours it but iOS Safari/WebKit ignores it on
            <textPath> and falls back to the alphabetic baseline. So we use no
            baseline attribute (alphabetic is the universal default) and let geometry
            centre it: because both bands' glyphs extend toward the centre here, an
            r=76 path lands each band centred on r≈70 — concentric in every engine.
            (See scripts/wordmark-measure.mjs.) */}
        <defs>
          <path id={id + "t"} d="M176,100 a76,76 0 1,0 -152,0" fill="none" />
          <path id={id + "b"} d="M24,100 a76,76 0 0,0 152,0" fill="none" />
        </defs>
        <Box
          component="text"
          sx={{ fontFamily: (t) => t.extra.typography.logo, fill: "text.primary" }}
          fontWeight={700}
          fontSize={22}
          letterSpacing={1.5}
        >
          <textPath href={"#" + id + "t"} startOffset="50%" textAnchor="middle">
            {text}
          </textPath>
        </Box>
        <Box
          component="text"
          sx={{ fontFamily: (t) => t.extra.typography.logo, fill: "text.primary" }}
          fontWeight={700}
          fontSize={22}
          letterSpacing={1.5}
        >
          <textPath href={"#" + id + "b"} startOffset="50%" textAnchor="middle">
            {text}
          </textPath>
        </Box>
      </Box>
      {icon.mode !== "none" && (
        <Box sx={{ position: "absolute", inset: 0, display: "grid", placeItems: "center" }}>
          {icon.mode === "custom" && icon.url ? (
            // Plain <img>: a small decorative mark, fit (not cropped) into a
            // square so any aspect ratio centers cleanly inside the ring.
            <Box
              component="img"
              src={icon.url}
              alt=""
              aria-hidden
              sx={{ width: size * 0.34, height: size * 0.34, objectFit: "contain", display: "block" }}
            />
          ) : icon.mode === "svg" && icon.svg ? (
            // The AI-designed mark. Only the server-sanitised form is ever
            // stored (allowlist-rebuild, fill=currentColor — app/ai/svg.py),
            // which is what makes this innerHTML safe to set.
            <Box
              component="svg"
              viewBox="0 0 100 100"
              aria-hidden
              sx={{ width: size * 0.3, height: size * 0.3, color: "text.primary", display: "block" }}
              dangerouslySetInnerHTML={{ __html: icon.svg }}
            />
          ) : (
            <CatGlyph size={size * 0.26} />
          )}
        </Box>
      )}
    </Box>
  );
}
