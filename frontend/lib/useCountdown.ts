"use client";

import { useEffect, useState } from "react";

export interface Countdown {
  d: number;
  h: number;
  m: number;
  s: number;
  done: boolean;
}

function calc(targetMs: number): Countdown {
  const ms = Math.max(0, targetMs - Date.now());
  return {
    d: Math.floor(ms / 86400000),
    h: Math.floor((ms % 86400000) / 3600000),
    m: Math.floor((ms % 3600000) / 60000),
    s: Math.floor((ms % 60000) / 1000),
    done: ms === 0,
  };
}

/**
 * Live countdown to an ISO target. Starts ticking after mount (so the first
 * client render matches the server's, avoiding a hydration mismatch). Returns
 * zeros until then.
 */
export function useCountdown(targetISO: string): Countdown {
  const targetMs = new Date(targetISO).getTime();
  const [t, setT] = useState<Countdown>({ d: 0, h: 0, m: 0, s: 0, done: false });

  useEffect(() => {
    if (Number.isNaN(targetMs)) return;
    // The tick lives in a handler (not the effect body) so the synchronous first
    // update doesn't trip react-hooks/set-state-in-effect, same as ScrollProgress.
    const tick = () => setT(calc(targetMs));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [targetMs]);

  return t;
}

/**
 * Build an ISO instant from the event's stored date + start time. The venue is in
 * Singapore (fixed +08:00, no DST), so we anchor the countdown there regardless of
 * the guest's own timezone.
 */
export function eventTargetISO(dateIso?: string, startTime?: string): string {
  if (!dateIso) return "";
  const time = (startTime ?? "00:00").slice(0, 5);
  return `${dateIso}T${time}:00+08:00`;
}
