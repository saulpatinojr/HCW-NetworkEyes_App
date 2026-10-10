import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { checkRateLimit } from "./rate-limit";

describe("checkRateLimit", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-23T00:00:00Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("allows up to the limit then denies within the window", async () => {
    const user = `u-${Math.random()}`;
    for (let i = 0; i < 5; i++) {
      expect(await checkRateLimit(user, "startDiscovery")).toBe(true);
    }
    expect(await checkRateLimit(user, "startDiscovery")).toBe(false);
  });

  it("keys independently per action", async () => {
    const user = `u-${Math.random()}`;
    for (let i = 0; i < 5; i++) await checkRateLimit(user, "actionA");
    expect(await checkRateLimit(user, "actionA")).toBe(false);
    // A different action for the same user still has its own budget.
    expect(await checkRateLimit(user, "actionB")).toBe(true);
  });

  it("keys independently per user", async () => {
    const a = `a-${Math.random()}`;
    const b = `b-${Math.random()}`;
    for (let i = 0; i < 5; i++) await checkRateLimit(a, "act");
    expect(await checkRateLimit(a, "act")).toBe(false);
    expect(await checkRateLimit(b, "act")).toBe(true);
  });

  it("resets after the window elapses", async () => {
    const user = `u-${Math.random()}`;
    for (let i = 0; i < 5; i++) await checkRateLimit(user, "act");
    expect(await checkRateLimit(user, "act")).toBe(false);
    // Advance past the default 60s window.
    vi.advanceTimersByTime(60_001);
    expect(await checkRateLimit(user, "act")).toBe(true);
  });

  it("honours a custom limit", async () => {
    const user = `u-${Math.random()}`;
    expect(await checkRateLimit(user, "act", 2)).toBe(true);
    expect(await checkRateLimit(user, "act", 2)).toBe(true);
    expect(await checkRateLimit(user, "act", 2)).toBe(false);
  });
});
