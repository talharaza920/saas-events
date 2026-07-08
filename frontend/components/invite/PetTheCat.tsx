"use client";

import Box from "@mui/material/Box";
import Snackbar from "@mui/material/Snackbar";
import { useEffect, useState } from "react";

// ↑ ↑ ↓ ↓ ← → ← → B A — the konami code. Tap it out (or arrow-key it) to pet the cat.
const KONAMI = [
  "ArrowUp",
  "ArrowUp",
  "ArrowDown",
  "ArrowDown",
  "ArrowLeft",
  "ArrowRight",
  "ArrowLeft",
  "ArrowRight",
  "b",
  "a",
];

type Paw = { id: number; left: number; delay: number };

/**
 * A subtle, on-brand easter egg: enter the konami code and the cat purrs — a small
 * shower of paw-prints rains down and a toast pops. Pure decoration, mounted on
 * the invite. No effect on the rest of the page.
 */
export default function PetTheCat() {
  const [open, setOpen] = useState(false);
  const [paws, setPaws] = useState<Paw[]>([]);

  useEffect(() => {
    let progress = 0;
    const onKey = (e: KeyboardEvent) => {
      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
      progress = key === KONAMI[progress] ? progress + 1 : key === KONAMI[0] ? 1 : 0;
      if (progress === KONAMI.length) {
        progress = 0;
        // setState in an event handler — fine under react-hooks rules.
        setPaws(
          Array.from({ length: 14 }, (_, i) => ({
            id: Date.now() + i,
            left: Math.random() * 100,
            delay: Math.random() * 0.6,
          })),
        );
        setOpen(true);
        window.setTimeout(() => setPaws([]), 2600);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <Box
        aria-hidden
        sx={{
          position: "fixed",
          inset: 0,
          pointerEvents: "none",
          zIndex: (t) => t.zIndex.snackbar - 1,
          overflow: "hidden",
        }}
      >
        {paws.map((p) => (
          <Box
            key={p.id}
            component="span"
            sx={{
              position: "absolute",
              top: -40,
              left: `${p.left}%`,
              fontSize: 28,
              animation: "pawfall 2.4s ease-in forwards",
              animationDelay: `${p.delay}s`,
              "@keyframes pawfall": {
                "0%": { transform: "translateY(0) rotate(0deg)", opacity: 0 },
                "10%": { opacity: 1 },
                "100%": { transform: "translateY(105vh) rotate(40deg)", opacity: 0 },
              },
            }}
          >
            🐾
          </Box>
        ))}
      </Box>
      <Snackbar
        open={open}
        autoHideDuration={2600}
        onClose={() => setOpen(false)}
        message="🐾 The cat purrs. You found the secret!"
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      />
    </>
  );
}
