"use client";

import Box from "@mui/material/Box";
import { keyframes } from "@mui/system";

import CatGlyph from "./CatGlyph";

const bounce = keyframes`0%,100%{transform:translateY(0)} 50%{transform:translateY(-6px)}`;
const peek = keyframes`0%,90%,100%{transform:rotate(0)} 45%{transform:rotate(-7deg)}`;

export type MascotMood = "idle" | "peek" | "happy";

/**
 * Mascot guide badge — the brand cat glyph in an ink ring with a periwinkle
 * collar tag. `mood` drives a small idle animation: the RSVP guide uses `peek`
 * while collecting answers and `happy` on success.
 */
export default function MascotBadge({
  size = 64,
  mood = "idle",
  invert = false,
  imageUrl,
}: {
  size?: number;
  mood?: MascotMood;
  /** Dark-background variant (footer): paper ring on ink. */
  invert?: boolean;
  /**
   * Optional uploaded photo to show inside the ring instead of the cat glyph
   * (e.g. the RSVP guide circle). Cropped to fill the circle; the ink ring and
   * collar tag stay so it still reads as the mascot badge.
   */
  imageUrl?: string;
}) {
  const anim = mood === "happy" ? bounce : mood === "peek" ? peek : "none";
  const dur = mood === "happy" ? "1.1s" : "3.4s";
  return (
    <Box
      sx={{
        position: "relative",
        display: "inline-grid",
        placeItems: "center",
        width: size,
        height: size,
        // Keep the square aspect when used as a flex item next to wrapping text
        // (e.g. the RSVP guide row on mobile) — otherwise it shrinks into an oval.
        flex: "none",
        animation: anim === "none" ? "none" : `${anim} ${dur} ease-in-out infinite`,
        "@media (prefers-reduced-motion: reduce)": { animation: "none" },
      }}
    >
      <Box
        sx={{
          width: "100%",
          height: "100%",
          borderRadius: "50%",
          display: "grid",
          placeItems: "center",
          bgcolor: invert ? "text.primary" : "background.default",
          border: "2px solid",
          borderColor: invert ? "background.default" : "text.primary",
          boxShadow: (t) => t.extra.shadows.soft,
          overflow: "hidden",
        }}
      >
        {imageUrl ? (
          <Box
            component="img"
            src={imageUrl}
            alt=""
            aria-hidden
            sx={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
          />
        ) : (
          <CatGlyph size={size * 0.56} sx={{ color: invert ? "background.default" : "text.primary" }} />
        )}
      </Box>
      {/* Collar tag — the glyph's brand signature. Hidden behind an uploaded photo,
          which is self-contained and reads cleaner without a dot on top. */}
      {!imageUrl && (
      <Box
        sx={{
          position: "absolute",
          bottom: 2,
          right: 6,
          width: "26%",
          height: "26%",
          minWidth: 12,
          minHeight: 12,
          bgcolor: "secondary.main",
          border: "2px solid",
          borderColor: invert ? "background.default" : "text.primary",
          borderRadius: "50%",
        }}
      />
      )}
    </Box>
  );
}
