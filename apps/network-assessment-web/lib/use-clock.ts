"use client";

import { useSyncExternalStore } from "react";

const TICK_MS = 30_000;

function subscribe(onChange: () => void) {
  const id = setInterval(onChange, TICK_MS);
  return () => clearInterval(id);
}

function snapshot(): number {
  return Math.floor(Date.now() / TICK_MS) * TICK_MS;
}

/**
 * The current time, rounded to 30 s, safe to read during render.
 *
 * `Date.now()` in a component body is impure (react-hooks/purity) and would
 * also make the server HTML disagree with the first client render. Reading the
 * clock through an external store fixes both: the value only changes on the
 * tick, and the server snapshot is 0, so time-relative badges ("just
 * completed") never render in HTML and appear after hydration.
 */
export function useCoarseNow(): number {
  return useSyncExternalStore(subscribe, snapshot, () => 0);
}
