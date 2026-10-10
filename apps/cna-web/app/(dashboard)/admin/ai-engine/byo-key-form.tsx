"use client";

import { useActionState } from "react";

import {
  clearByoApiKeyAction,
  setByoApiKeyAction,
  type ByoKeyActionState,
} from "@/app/(dashboard)/admin/ai-engine/actions";

const buttonClass =
  "rounded-lg px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:bg-navy-200 disabled:text-navy-500 dark:disabled:bg-navy-700 dark:disabled:text-navy-400";

function Feedback({ state }: { state: ByoKeyActionState }) {
  if (!state) return null;
  if (state.error) {
    return (
      <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
        {state.error}
      </p>
    );
  }
  if (state.success) {
    return (
      <p className="mt-3 rounded-xl border border-teal-200 bg-teal-50 p-3 text-sm text-teal-800">
        {state.success}
      </p>
    );
  }
  return null;
}

export function ByoKeyForm({
  provider,
  label,
  configured,
  isAdmin,
}: {
  provider: "anthropic" | "openai";
  label: string;
  configured: boolean;
  isAdmin: boolean;
}) {
  const [saveState, saveAction, saving] = useActionState(setByoApiKeyAction, null);
  const [clearState, clearAction, clearing] = useActionState(clearByoApiKeyAction, null);

  return (
    <div className="mt-6 space-y-3">
      <form action={saveAction} className="flex flex-col gap-3 sm:flex-row">
        <input type="hidden" name="provider" value={provider} />
        <input
          type="password"
          name="apiKey"
          autoComplete="off"
          spellCheck={false}
          placeholder={configured ? `Replace ${label} key` : `Paste ${label} API key`}
          disabled={!isAdmin || saving}
          className="flex-1 rounded-lg border border-navy-200 bg-white px-3 py-2 font-mono text-sm text-navy-900 placeholder:text-navy-400 disabled:bg-navy-50 dark:border-navy-700 dark:bg-navy-950 dark:text-white"
        />
        <button
          type="submit"
          disabled={!isAdmin || saving}
          className={`${buttonClass} bg-navy-900 text-white hover:bg-navy-700 dark:bg-teal-500 dark:text-navy-950 dark:hover:bg-teal-400`}
        >
          {saving ? "Verifying…" : configured ? "Replace key" : "Save key"}
        </button>
      </form>
      <Feedback state={saveState} />

      {configured && (
        <form action={clearAction}>
          <input type="hidden" name="provider" value={provider} />
          <button
            type="submit"
            disabled={!isAdmin || clearing}
            className={`${buttonClass} border border-navy-200 bg-white text-navy-700 hover:bg-navy-50 dark:border-navy-700 dark:bg-navy-900 dark:text-navy-100`}
          >
            {clearing ? "Removing…" : "Clear key"}
          </button>
        </form>
      )}
      <Feedback state={clearState} />
    </div>
  );
}
