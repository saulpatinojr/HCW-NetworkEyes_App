"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { generateDiagramFromDiscovery } from "./actions";

/**
 * Builds the diagram from discovered topology and reloads the editor with it.
 * Generation is a single server round trip (the Python engine is deterministic
 * — no AI calls), so a plain transition is enough here; there is no long-running
 * background job to poll.
 */
export function GenerateDiagramButton({ engagementId }: { engagementId: string }) {
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const router = useRouter();

  function handleClick() {
    setError(null);
    setDone(null);
    startTransition(async () => {
      const result = await generateDiagramFromDiscovery(engagementId);
      if (result.error) {
        setError(result.error);
        return;
      }
      const pages = result.pageCount ?? 0;
      setDone(
        pages > 0
          ? `Generated ${pages} page${pages === 1 ? "" : "s"} from discovery.`
          : "Diagram generated from discovery.",
      );
      router.refresh();
    });
  }

  return (
    <div className="flex flex-col items-start gap-2">
      <button
        type="button"
        onClick={handleClick}
        disabled={isPending}
        className="inline-flex items-center gap-2 rounded-lg bg-teal-600 px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-teal-500 disabled:opacity-60"
      >
        {isPending ? (
          <>
            <svg aria-hidden="true" focusable="false" className="h-4 w-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Generating…
          </>
        ) : (
          <>
            <svg aria-hidden="true" focusable="false" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h10M4 18h7" />
            </svg>
            Generate from discovery
          </>
        )}
      </button>
      {done && <p className="text-xs text-teal-700 dark:text-teal-300">{done}</p>}
      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600 dark:border-red-800/40 dark:bg-red-900/10 dark:text-red-400">
          {error}
        </p>
      )}
    </div>
  );
}
