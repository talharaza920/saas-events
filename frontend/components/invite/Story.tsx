"use client";

import { useState } from "react";

import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import { useTheme } from "@mui/material/styles";
import type { SxProps, Theme } from "@mui/material/styles";
import Typography from "@mui/material/Typography";
import Image from "next/image";

import type { StoryBeat, StoryClimax, StoryContent, StorySectionContent } from "@/lib/content";

import Paw from "./brand/Paw";
import RichText from "./RichText";
import Section from "./Section";

/**
 * Feathered edge mask: two crossed gradients (intersected) fade all four sides
 * of the image to transparent, so the panel dissolves into the cream page
 * instead of sitting in a hard box. The fade distance comes from the
 * `storyFeather` theme token (% per edge); `#000` is mask alpha, not a color.
 */
function featherMask(feather: number) {
  const stops = `transparent 0, #000 ${feather}%, #000 ${100 - feather}%, transparent 100%`;
  const layers = `linear-gradient(to right, ${stops}), linear-gradient(to bottom, ${stops})`;
  return {
    WebkitMaskImage: layers,
    maskImage: layers,
    WebkitMaskComposite: "source-in",
    maskComposite: "intersect",
  } as const;
}

/** A manga panel: an edge-feathered image that dissolves into the page. */
function PanelFrame({ beat, alt, wide, priority }: { beat: { image?: string }; alt: string; wide?: boolean; priority?: boolean }) {
  const theme = useTheme();
  const mask = featherMask(theme.extra.storyFeather);
  return (
    <Box
      sx={{
        position: "relative",
        aspectRatio: wide ? "16 / 9" : "4 / 3",
      }}
    >
      {beat.image && (
        <Image src={beat.image} alt={alt} fill priority={priority} sizes="(max-width: 760px) 100vw, 50vw" style={{ objectFit: "cover", ...mask }} />
      )}
    </Box>
  );
}

/** Narration block — bullet number + storybook caption. */
function Narration({ label, text }: { label: React.ReactNode; text?: string }) {
  return (
    <Stack spacing={1.5} sx={{ justifyContent: "center" }}>
      <Typography sx={{ fontFamily: (t) => t.extra.typography.display, fontWeight: 800, color: "primary.main", fontSize: 15, letterSpacing: "0.12em" }}>
        {label}
      </Typography>
      <Typography
        variant="subtitle1"
        sx={{ fontSize: { xs: "1.25rem", md: "1.7rem" }, lineHeight: 1.5, color: "text.primary" }}
      >
        <RichText text={text} />
      </Typography>
    </Stack>
  );
}

/** One alternating-side beat (image + narration). Numbered by position. */
function Beat({ beat, num, flip, priority }: { beat: StoryBeat; num: string; flip: boolean; priority?: boolean }) {
  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: { xs: "1fr", md: flip ? ".95fr 1.05fr" : "1.05fr .95fr" },
        gap: { xs: 3, md: 7 },
        alignItems: "center",
      }}
    >
      {/* On mobile the narration (number + description) sits ABOVE the image:
          the image takes order 1 so the default-order-0 narration renders first.
          Desktop is unchanged — the md orders still alternate image left/right. */}
      <Box sx={{ order: { xs: 1, md: flip ? 2 : 0 } }}>
        <PanelFrame beat={beat} alt={`Story panel ${num}`} wide={beat.wide} priority={priority} />
      </Box>
      <Narration label={num} text={beat.text} />
    </Box>
  );
}

/** The "Chapter Two" climax that leads into the RSVP. `flip` continues the
 * alternating layout from the last numbered beat so it lands on the opposite side. */
function Climax({ climax, flip }: { climax: StoryClimax; flip: boolean }) {
  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: { xs: "1fr", md: flip ? ".95fr 1.05fr" : "1.05fr .95fr" },
        gap: { xs: 3, md: 7 },
        alignItems: "center",
        mt: { xs: 4, md: 7 },
      }}
    >
      {/* On mobile the narration (number + description) sits ABOVE the image:
          the image takes order 1 so the default-order-0 narration renders first.
          Desktop is unchanged — the md orders still alternate image left/right. */}
      <Box sx={{ order: { xs: 1, md: flip ? 2 : 0 } }}>
        <PanelFrame beat={{ image: climax.image }} alt="The big announcement" wide />
      </Box>
      <Stack spacing={2} sx={{ justifyContent: "center", alignItems: "flex-start" }}>
        {climax.label && (
          <Typography sx={{ fontFamily: (t) => t.extra.typography.display, fontWeight: 800, color: "primary.main", fontSize: 15, letterSpacing: "0.12em" }}>
            {climax.label}
          </Typography>
        )}
        <Typography variant="subtitle1" sx={{ fontSize: { xs: "1.25rem", md: "1.7rem" }, lineHeight: 1.5 }}>
          <RichText text={climax.text} />
        </Typography>
        {climax.cta && (
          <Button href="#rsvp" variant="contained" color="primary" size="large" sx={{ borderRadius: 999, mt: 1 }} startIcon={<Paw size={18} sx={{ color: "#fff" }} />}>
            {climax.cta}
          </Button>
        )}
      </Stack>
    </Box>
  );
}

/** One arc's "How a cat wrote our story" — the image-driven manga strip.
 * `sx` is forwarded to the Section (the carousel uses it to trim the top padding,
 * since the chapter controls above already supply that breathing room). */
function StoryArcView({ story, sx }: { story: StoryContent; sx?: SxProps<Theme> }) {
  return (
    <Section id="story" kicker={story.kicker} heading={story.heading} intro={story.intro} maxWidth="lg" bg="background.paper" sx={sx}>
      <Stack spacing={{ xs: 4, md: 6 }}>
        {story.beats.map((beat, i) => (
          <Beat key={i} beat={beat} num={String(i + 1).padStart(2, "0")} flip={i % 2 === 1} priority={i === 0} />
        ))}
      </Stack>
      {story.climax && <Climax climax={story.climax} flip={story.beats.length % 2 === 1} />}
    </Section>
  );
}

/** The subtle section label above the story (e.g. "Our story"). A muted, letter-
 * spaced eyebrow in the secondary brand tone — present so the section reads as a
 * titled block without competing with each arc's own kicker/heading below it.
 * It carries the section's top breathing room so the story body can trim its own. */
function StorySectionLabel({ text }: { text: string }) {
  return (
    <Box sx={{ bgcolor: "background.paper", textAlign: "center", pt: { xs: 9, sm: 14, md: 16 } }}>
      <Typography
        component="p"
        sx={{
          color: "secondary.main",
          fontWeight: 600,
          fontSize: { xs: 13, md: 14 },
          letterSpacing: "0.28em",
          textTransform: "uppercase",
        }}
      >
        {text}
      </Typography>
    </Box>
  );
}

/** Prev/next + dot indicator for switching between multiple arcs. Rendered both
 * above and below the arc body so the chapter switch is reachable without
 * scrolling past the whole story first. */
function CarouselControls({
  count,
  active,
  onGo,
  onSelect,
  sx,
}: {
  count: number;
  active: number;
  onGo: (dir: -1 | 1) => void;
  onSelect: (i: number) => void;
  sx?: SxProps<Theme>;
}) {
  return (
    <Box sx={[{ display: "flex", justifyContent: "center" }, ...(Array.isArray(sx) ? sx : [sx])]}>
      <Stack direction="row" spacing={1.5} alignItems="center">
        <IconButton aria-label="Previous chapter" onClick={() => onGo(-1)} sx={{ color: "primary.main" }}>
          <ChevronLeftIcon />
        </IconButton>
        <Stack direction="row" spacing={1} alignItems="center">
          {Array.from({ length: count }).map((_, j) => (
            <Box
              key={j}
              component="button"
              aria-label={`Go to chapter ${j + 1}`}
              onClick={() => onSelect(j)}
              sx={{
                p: 0,
                border: 0,
                cursor: "pointer",
                width: j === active ? 22 : 9,
                height: 9,
                borderRadius: 999,
                bgcolor: j === active ? "primary.main" : "primary.light",
                opacity: j === active ? 1 : 0.5,
                transition: "all .25s ease",
              }}
            />
          ))}
        </Stack>
        <IconButton aria-label="Next chapter" onClick={() => onGo(1)} sx={{ color: "primary.main" }}>
          <ChevronRightIcon />
        </IconButton>
      </Stack>
    </Box>
  );
}

/** The arc body wrapped with chapter controls above and below it. When a section
 * `label` is supplied it sits at the very top and supplies the section's top
 * padding, so the first set of controls trims its own. */
function StoryCarousel({ stories, label }: { stories: StoryContent[]; label?: string }) {
  const [i, setI] = useState(0);
  const count = stories.length;
  const go = (dir: -1 | 1) => setI((prev) => (prev + dir + count) % count);
  return (
    <Box sx={{ bgcolor: "background.paper" }}>
      {label && <StorySectionLabel text={label} />}
      <CarouselControls
        count={count}
        active={i}
        onGo={go}
        onSelect={setI}
        sx={{ pt: label ? { xs: 3, md: 4 } : { xs: 9, sm: 14, md: 16 }, pb: { xs: 2, md: 4 } }}
      />
      {/* Section's own top padding is trimmed — the controls above already give
          the gap, so the heading sits a comfortable distance below them. */}
      <StoryArcView story={stories[i]} sx={{ pt: { xs: 1, md: 2 } }} />
      <CarouselControls
        count={count}
        active={i}
        onGo={go}
        onSelect={setI}
        sx={{ pb: { xs: 6, md: 9 }, mt: { xs: -2, md: -4 } }}
      />
    </Box>
  );
}

/**
 * The story section. One arc renders exactly as before; multiple visible arcs
 * become a subtle carousel. Arc selection happens server-side (per-guest
 * targeting by arc id) — this component just renders whatever it's handed.
 *
 * `sectionLabel` is the optional "Our story" eyebrow above it all; it only shows
 * when toggled on AND given a non-blank label, and when present it supplies the
 * section's top padding so the body below trims its own (no doubled gap).
 */
export default function Story({
  stories,
  sectionLabel,
}: {
  stories: StoryContent[];
  sectionLabel?: StorySectionContent;
}) {
  const renderable = stories.filter((s) => s.heading || s.beats.length > 0);
  if (renderable.length === 0) return null;
  const label =
    sectionLabel && sectionLabel.visible !== false ? (sectionLabel.label ?? "").trim() : "";

  if (renderable.length > 1) return <StoryCarousel stories={renderable} label={label || undefined} />;
  if (!label) return <StoryArcView story={renderable[0]} />;
  return (
    <Box sx={{ bgcolor: "background.paper" }}>
      <StorySectionLabel text={label} />
      <StoryArcView story={renderable[0]} sx={{ pt: { xs: 4, md: 5 } }} />
    </Box>
  );
}
