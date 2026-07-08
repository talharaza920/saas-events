"use client";

import Box from "@mui/material/Box";
import { useEffect, useState } from "react";

/**
 * A slim scroll-progress bar pinned to the top of the invite, with a little paw
 * (🐾) that pads along as the mascot "walks" the guest down the page. On-brand polish;
 * theme-colored, no hardcoded palette.
 */
export default function ScrollProgress() {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    // setState lives in the scroll handler (an event handler — allowed), not in
    // the effect body, so this doesn't trip react-hooks/set-state-in-effect.
    const onScroll = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      setProgress(max > 0 ? Math.min(window.scrollY / max, 1) : 0);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  return (
    <Box
      aria-hidden
      sx={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        height: 4,
        zIndex: (t) => t.zIndex.appBar + 1,
        pointerEvents: "none",
      }}
    >
      <Box
        sx={{
          height: "100%",
          width: `${progress * 100}%`,
          bgcolor: "primary.main",
          transition: "width 80ms linear",
        }}
      />
      <Box
        component="span"
        sx={{
          position: "absolute",
          top: -2,
          left: `calc(${progress * 100}% - 10px)`,
          fontSize: 14,
          lineHeight: 1,
          transition: "left 80ms linear",
        }}
      >
        🐾
      </Box>
    </Box>
  );
}
