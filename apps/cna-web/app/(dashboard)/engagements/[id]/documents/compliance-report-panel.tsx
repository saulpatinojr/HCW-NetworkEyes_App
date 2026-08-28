"use client";

import { useActionState, useState } from "react";
import { runComplianceCheck, runAllComplianceChecks } from "./actions";
import { SubmitButton } from "@/components/ui/submit-button";

const FRAMEWORKS = [
  { value: "nist",  label: "NIST SP 800-53 Rev 5",                    desc: "Federal security controls for US government and critical infrastructure" },
  { value: "cis",   label: "CIS Azure Foundations Benchmark v2.0",     desc: "Prescriptive security configuration guidance for Azure" },
  { value: "soc2",  label: "SOC 2 Type II (Trust Services Criteria)",  desc: "Security, availability, and confidentiality for service organizations" },
  { value: "hipaa", label: "HIPAA Security Rule",                       desc: "Healthcare data security controls for ePHI protection" },
  { value: "pci",   label: "PCI-DSS v4.0",                             desc: "Payment card industry data security standards" },
  { value: "waf",   label: "Azure Well-Architected Framework (Security)", desc: "Microsoft security pillar best practices for Azure workloads" },
] as const;

type Framework = (typeof FRAMEWORKS)[number]["value"];

interface Props {
  engagementId: string;
  hasTopology: boolean;
  needsResync?: boolean;
}

const CARD_BASE =
  "flex cursor-pointer items-start gap-3 rounded-xl border border-navy-700 bg-navy-50 dark:bg-navy-800/30 p-3 transition-colors hover:border-teal-600/60 hover:bg-teal-50 dark:hover:bg-teal-900/20";

export function ComplianceReportPanel({ engagementId, hasTopology, needsResync }: Props) {
  const [framework, setFramework] = useState<Framework>("nist");
  const [state, action, isPending] = useActionState(runComplianceCheck, null);
  const [allState, allAction] = useActionState(runAllComplianceChecks, null);

  return (
    <section className="glass p-6">
      <h2 className="mb-1 text-lg font-semibold text-navy-800 dark:text-navy-100">Compliance Check</h2>
      <p className="mb-5 text-sm text-navy-400">
        Run a framework-specific compliance gap analysis against your discovered network
        topology. Results are saved as findings with framework control mappings.
      </p>

      {!hasTopology && (
        <p className="mb-4 rounded-lg border border-amber-800/40 bg-amber-50 dark:bg-amber-900/20 px-4 py-3 text-sm text-amber-600 dark:text-amber-400">
          No discovery data yet. Run discovery on the Connections tab first.
        </p>
      )}

      {needsResync && hasTopology && (
        <div className="mb-4 flex items-center gap-3 rounded-lg border border-amber-700/40 bg-amber-50 dark:bg-amber-900/20 px-4 py-3">
          <svg aria-hidden="true" focusable="false" className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm0-2a6 6 0 110-12 6 6 0 010 12zm-1-9a1 1 0 112 0v4a1 1 0 11-2 0V7zm0 6a1 1 0 112 0 1 1 0 01-2 0z" clipRule="evenodd" />
          </svg>
          <p className="text-sm text-amber-700 dark:text-amber-300">
            <span className="font-semibold">Subscriptions changed</span> — re-sync before running compliance checks.
          </p>
        </div>
      )}

      {/* ── Single framework form ── */}
      <form action={action} className="space-y-4">
        <input type="hidden" name="engagementId" value={engagementId} />

        <fieldset>
          <legend className="label-caps mb-2 block text-navy-500">
            Compliance Framework
          </legend>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {FRAMEWORKS.map((fw) => (
              <label
                key={fw.value}
                className={`${CARD_BASE} ${
                  framework === fw.value
                    ? "!border-teal-500 !bg-teal-50 dark:bg-teal-900/30"
                    : ""
                }`}
              >
                <input
                  type="radio"
                  name="framework"
                  value={fw.value}
                  checked={framework === fw.value}
                  onChange={() => setFramework(fw.value)}
                  className="mt-0.5 accent-teal-500"
                />
                <div>
                  <p className="text-xs font-semibold text-navy-800 dark:text-navy-100">{fw.label}</p>
                  <p className="mt-0.5 text-xs text-navy-400">{fw.desc}</p>
                </div>
              </label>
            ))}
          </div>
        </fieldset>

        <p className="text-xs text-navy-500">
          Analysis uses live topology data, uploaded documents, and existing findings as
          context. Duplicate findings are not re-created.
        </p>

        {state?.error && (
          <p className="rounded-lg border border-red-800/40 bg-red-50 dark:bg-red-900/20 px-4 py-2 text-sm text-red-600 dark:text-red-400">
            {state.error}
          </p>
        )}
        {state?.success && (
          <p className="rounded-lg border border-teal-800/40 bg-teal-50 dark:bg-teal-900/20 px-4 py-2 text-sm text-teal-700 dark:text-teal-300">
            ✓ Compliance check complete —{" "}
            <strong className="text-teal-800 dark:text-teal-200">{state.count}</strong> finding
            {state.count !== 1 ? "s" : ""} added with framework control mappings.
          </p>
        )}

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={isPending || !hasTopology}
            className="inline-flex items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-teal-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isPending ? (
              <>
                <svg aria-hidden="true" focusable="false" className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Running compliance check…
              </>
            ) : (
              <>
                <svg aria-hidden="true" focusable="false" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Run compliance check
              </>
            )}
          </button>
        </div>
      </form>

      {/* ── Run All Checks form ── */}
      <div className="border-t border-navy-700/40 pt-4 mt-4">
        <form action={allAction}>
          <input type="hidden" name="engagementId" value={engagementId} />

          {allState?.error && (
            <p className="mb-3 rounded-xl border border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-600 dark:text-red-400">
              {allState.error}
            </p>
          )}
          {allState?.success && (
            <p className="mb-3 rounded-xl border border-teal-800 bg-teal-50 dark:bg-teal-900/20 px-4 py-3 text-sm text-teal-700 dark:text-teal-300">
              All checks complete —{" "}
              <strong className="text-teal-800 dark:text-teal-200">{allState.count}</strong> unique new
              finding{allState.count !== 1 ? "s" : ""} generated across all 6 frameworks.
            </p>
          )}

          <div className="flex items-center justify-between gap-4 rounded-xl border border-navy-700/40 bg-navy-50 dark:bg-navy-800/20 px-4 py-3">
            <div>
              <p className="text-xs font-semibold text-navy-500 dark:text-navy-200">Run All Checks</p>
              <p className="mt-0.5 text-xs text-navy-500">
                Runs all 6 frameworks in parallel. May take a few minutes.
              </p>
            </div>
            <SubmitButton
              loadingText="Running all…"
              className="shrink-0 bg-navy-700 hover:bg-navy-600 focus:ring-navy-500"
            >
              Run all checks
            </SubmitButton>
          </div>
        </form>
      </div>
    </section>
  );
}
