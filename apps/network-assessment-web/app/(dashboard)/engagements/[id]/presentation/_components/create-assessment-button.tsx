"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createInteractiveAssessment } from "../../client-deliverables/actions";
import { getDeliverableProgress } from "../../deliverables/actions";

type Step = { stepId: string; label: string; status: string };

const POLL_MS = 4000;

// Generation is 12+ AI calls running under next/server after(), so the action
// returns immediately and this component polls the deliverable row for
// progress. Never await the generation here — that is what the ingress
// timeout kills.
export function CreateInteractiveAssessmentButton({
  engagementId,
  existing,
}: {
  engagementId: string;
  existing?: { id: string; status: string } | null;
}) {
  const router = useRouter();
  const wasRunning = existing?.status === "RUNNING" || existing?.status === "QUEUED";

  const [deliverableId, setDeliverableId] = useState<string | null>(wasRunning ? existing!.id : null);
  const [isRunning, setIsRunning] = useState(wasRunning);
  const [steps, setSteps] = useState<Step[]>([]);
  const [error, setError] = useState<string | null>(null);

  // The poll loop lives inside the effect: each tick schedules the next with
  // a timer the cleanup cancels, so a run can never stack timers, and every
  // setState happens after an await rather than synchronously in the effect.
  useEffect(() => {
    if (!isRunning || !deliverableId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function tick(id: string) {
      const result = await getDeliverableProgress(id);
      if (cancelled) return;
      if (!result) {
        // Row gone or access lost — leave the spinner to the next tick.
        timer = setTimeout(() => void tick(id), POLL_MS);
        return;
      }
      setSteps(result.steps as Step[]);

      if (result.status === "COMPLETED") {
        setIsRunning(false);
        router.refresh();
        return;
      }
      if (result.status === "FAILED") {
        setIsRunning(false);
        const fatal = result.steps.find((s) => s.stepId === "fatal");
        setError(fatal?.label ?? "AI generation failed — the full error has been logged.");
        return;
      }
      timer = setTimeout(() => void tick(id), POLL_MS);
    }

    void tick(deliverableId);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [isRunning, deliverableId, router]);

  async function handleClick() {
    setError(null);
    setSteps([]);
    setIsRunning(true);
    const result = await createInteractiveAssessment(engagementId);
    if (result.error || !result.deliverableId) {
      setIsRunning(false);
      setError(result.error ?? "Could not start generation.");
      return;
    }
    setDeliverableId(result.deliverableId);
  }

  const done = steps.filter((s) => s.status === "done").length;
  const total = steps.length;
  const current = steps.find((s) => s.status === "running");

  return (
    <div className="flex flex-col items-start gap-2">
      <button
        type="button"
        onClick={handleClick}
        disabled={isRunning}
        className="inline-flex items-center gap-2 rounded-lg bg-teal-600 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-teal-500 disabled:opacity-60"
      >
        {isRunning ? (
          <>
            <svg aria-hidden="true" focusable="false" className="h-4 w-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Generating with AI…
          </>
        ) : (
          <>
            <svg aria-hidden="true" focusable="false" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            {error ? "Retry generation" : "Create Interactive Assessment"}
          </>
        )}
      </button>

      {isRunning && (
        <p className="text-xs text-navy-500">
          {total > 0
            ? `Section ${Math.min(done + 1, total)} of ${total}${current ? ` — ${current.label}` : ""}`
            : "Starting generation — this runs in the background and takes several minutes."}
        </p>
      )}
      {isRunning && (
        <p className="text-xs text-navy-500">
          You can leave this page; generation continues and the site unlocks when it finishes.
        </p>
      )}

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600 dark:border-red-800/40 dark:bg-red-900/10 dark:text-red-400">
          {error}
        </p>
      )}
    </div>
  );
}
