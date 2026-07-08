"use client";

import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { DressCodeContent } from "@/lib/content";
import type { ThemeColors } from "@/theme/types";

import Section from "./Section";

/** A row of colored circles — each value is either a theme token name or a raw
 *  CSS colour (e.g. "#ff7a00"). When `avoid`, each gets a diagonal strike. */
function Swatches({ tokens, avoid }: { tokens: string[]; avoid?: boolean }) {
  return (
    <Stack direction="row" spacing={1.75} sx={{ justifyContent: "center", flexWrap: "wrap", rowGap: 1.75 }}>
      {tokens.map((token, i) => (
        <Box
          key={`${token}-${i}`}
          aria-hidden
          sx={{
            position: "relative",
            width: 54,
            height: 54,
            borderRadius: "50%",
            border: "2px solid",
            borderColor: "text.primary",
            // Theme token wins; otherwise treat the value as a raw CSS colour
            // (custom swatch added in the admin), falling back to paperEdge if empty.
            bgcolor: (t) => t.extra.colors[token as keyof ThemeColors] ?? (token || t.extra.colors.paperEdge),
            opacity: avoid ? 0.85 : 1,
            // Diagonal "not this" strike for the avoid row.
            ...(avoid && {
              "&::after": {
                content: '""',
                position: "absolute",
                inset: -2,
                borderRadius: "50%",
                background: (t) =>
                  `linear-gradient(135deg, transparent calc(50% - 1.5px), ${t.extra.colors.ink} calc(50% - 1.5px), ${t.extra.colors.ink} calc(50% + 1.5px), transparent calc(50% + 1.5px))`,
              },
            }),
          }}
        />
      ))}
    </Stack>
  );
}

/** Small caption above a swatch row. */
function RowLabel({ children }: { children: React.ReactNode }) {
  return (
    <Typography
      sx={{
        textAlign: "center",
        fontFamily: (t) => t.extra.typography.display,
        fontWeight: 800,
        color: "primary.main",
        fontSize: 14,
        letterSpacing: "0.12em",
        textTransform: "uppercase",
      }}
    >
      {children}
    </Typography>
  );
}

/** "Smart & breezy" — guidance + palettes of token-colored swatches (wear/avoid). */
export default function DressCode({ dressCode }: { dressCode: DressCodeContent }) {
  if (!dressCode.heading && !dressCode.body) return null;
  const hasWear = dressCode.swatches.length > 0;
  const hasAvoid = dressCode.swatches_avoid.length > 0;
  return (
    <Section
      id="dress"
      kicker={dressCode.kicker}
      heading={dressCode.heading}
      intro={dressCode.body}
      maxWidth="md"
      sx={{ background: (t) => `linear-gradient(180deg, ${t.extra.colors.paper} 0%, ${t.extra.colors.paperAlt} 100%)` }}
    >
      <Stack spacing={4}>
        {hasWear && (
          <Stack spacing={1.5}>
            {/* Only caption the "wear" row when there's an avoid row to contrast it. */}
            {hasAvoid && <RowLabel>{dressCode.wear_label ?? "Lovely on the day"}</RowLabel>}
            <Swatches tokens={dressCode.swatches} />
          </Stack>
        )}
        {hasAvoid && (
          <Stack spacing={1.5}>
            <RowLabel>{dressCode.avoid_label ?? "Best avoided"}</RowLabel>
            <Swatches tokens={dressCode.swatches_avoid} avoid />
          </Stack>
        )}
      </Stack>
    </Section>
  );
}
