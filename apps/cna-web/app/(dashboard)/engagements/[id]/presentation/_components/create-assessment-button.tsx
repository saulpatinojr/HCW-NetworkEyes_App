"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { createInteractiveAssessment } from "../../client-deliverables/actions";

export function CreateInteractiveAssessmentButton({ engagementId }: { engagementId: string }) {
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  function handleClick() {
    setError(null);
    startTransition(async () => {
      const result = await createInteractiveAssessment(engagementId);
      if (result.error) {
        setError(result.error);
      } else {
        router.refresh();
      }
    });
  }

  return (
    <div className="flex flex-col items-start gap-2">
      <button
        type="button"
        onClick={handleClick}
        disabled={isPending}
        className="inline-flex items-center gap-2 rounded-lg bg-teal-600 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-teal-500 disabled:opacity-60"
      >
        {isPending ? (
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
            Create Interactive Assessment
          </>
        )}
      </button>
      {isPending && (
        <p className="text-xs text-navy-500">
          AI is generating your assessment — this may take up to 60 seconds…
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
