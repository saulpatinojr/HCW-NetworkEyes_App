"use client";

// Polls generation progress for a background-generated deliverable (sectioned
// Comprehensive Assessment) — mirrors the connections-panel discovery pattern.
// The steady 3s poll also keeps the scale-to-zero dev replica alive while the
// background orchestrator runs.

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getDeliverableProgress } from "./actions";

interface Step {
  stepId: string;
  label: string;
  status: "pending" | "running" | "done" | "failed" | "skipped";
}

const POLL_MS = 3_000;

export function DeliverableProgress({ deliverableId }: { deliverableId: string }) {
  const router = useRouter();
  const [steps, setSteps] = useState<Step[]>([]);
  const [status, setStatus] = useState<string>("RUNNING");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback(async () => {
    const progress = await getDeliverableProgress(deliverableId).catch(() => null);
    if (!progress) return;
    setSteps(progress.steps as Step[]);
    setStatus(progress.status);
    if (progress.status === "COMPLETED" || progress.status === "FAILED") {
      if (timer.current) clearInterval(timer.current);
      router.refresh();
    }
  }, [deliverableId, router]);

  useEffect(() => {
    void poll();
    timer.current = setInterval(() => void poll(), POLL_MS);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [poll]);

  const done = steps.filter((s) => s.status === "done" || s.status === "skipped").length;
  const total = 14; // 12 domain sections + executive summary + assembly
  const running = steps.filter((s) => s.status === "running").map((s) => s.label);

  if (status === "FAILED") {
    return (
      <span className="rounded border border-red-800/40 bg-red-50 dark:bg-red-900/20 px-2 py-1 text-xs font-medium text-red-600 dark:text-red-400">
        Generation failed — delete and regenerate
      </span>
    );
  }

  return (
    <div className="flex items-center gap-2" aria-live="polite">
      <svg aria-hidden="true" className="h-3.5 w-3.5 animate-spin text-teal-700 dark:text-teal-400" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
      </svg>
      <div className="min-w-0">
        <p className="text-xs font-medium text-teal-700 dark:text-teal-300">
          Generating section {Math.min(done + 1, total)} of {total}
        </p>
        {running.length > 0 && (
          <p className="truncate text-xs text-navy-500">{running.join(" · ")}</p>
        )}
      </div>
    </div>
  );
}
