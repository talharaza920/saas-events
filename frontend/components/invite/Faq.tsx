"use client";

import Box from "@mui/material/Box";
import Collapse from "@mui/material/Collapse";
import Typography from "@mui/material/Typography";
import { useState } from "react";

import type { FaqContent } from "@/lib/content";

import RichText from "./RichText";
import Section from "./Section";

/** "Questions, answered" — an accordion FAQ; one item open at a time. */
export default function Faq({ faq }: { faq: FaqContent }) {
  const [open, setOpen] = useState(0);
  if (faq.items.length === 0) return null;

  return (
    <Section id="faq" kicker={faq.kicker} heading={faq.heading} maxWidth="md">
      <Box sx={{ maxWidth: 760, mx: "auto", display: "grid", gap: 1.5 }}>
        {faq.items.map((f, i) => {
          const isOpen = open === i;
          return (
            <Box
              key={i}
              sx={{
                border: "2px solid",
                borderColor: "text.primary",
                borderRadius: (t) => `${t.extra.radius}px`,
                bgcolor: "background.default",
                overflow: "hidden",
              }}
            >
              <Box
                component="button"
                onClick={() => setOpen(isOpen ? -1 : i)}
                aria-expanded={isOpen}
                sx={{
                  width: "100%",
                  textAlign: "left",
                  bgcolor: "transparent",
                  border: 0,
                  cursor: "pointer",
                  p: "20px 22px",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: 2,
                  fontFamily: (t) => t.extra.typography.display,
                  fontWeight: 700,
                  fontSize: 19,
                  color: "text.primary",
                }}
              >
                <Box component="span">
                  <RichText text={f.q} variant="inline" />
                </Box>
                <Box
                  component="span"
                  aria-hidden
                  sx={{
                    fontSize: 26,
                    lineHeight: 1,
                    color: "primary.main",
                    flex: "none",
                    transition: "transform .25s ease",
                    transform: isOpen ? "rotate(45deg)" : "none",
                  }}
                >
                  +
                </Box>
              </Box>
              <Collapse in={isOpen}>
                <Typography sx={{ px: "22px", pb: "20px", color: "text.secondary" }}>
                  <RichText text={f.a} />
                </Typography>
              </Collapse>
            </Box>
          );
        })}
      </Box>
    </Section>
  );
}
