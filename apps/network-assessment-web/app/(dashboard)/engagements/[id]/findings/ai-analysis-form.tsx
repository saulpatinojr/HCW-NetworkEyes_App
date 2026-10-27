"use client";

import { useActionState } from "react";
import { runAnalysis } from "../analysis/actions";
import { runAllAnalysis } from "../analysis/actions";
import { SubmitButton } from "@/components/ui/submit-button";

const ANALYSIS_OPTIONS = [
  {
    group: "Security Frameworks",
    items: [
      {
        value: "general",
        label: "General Security Review",
        desc: "Broad security posture across all categories — perimeter, segmentation, encryption, monitoring.",
      },
      {
        value: "zero_trust",
        label: "Zero Trust Assessment",
        desc: "Implicit trust zones, lateral movement risks, micro-segmentation gaps, identity-based network access.",
      },
      {
        value: "compliance_nist",
        label: "NIST SP 800-53",
        desc: "Map findings to NIST controls: SC-7 Boundary Protection, AC-4 Information Flow, SI-3 Malware.",
      },
      {
        value: "compliance_cis",
        label: "CIS Azure Benchmark",
        desc: "Evaluate against CIS Azure Foundations Benchmark v2.0 and CIS Controls v8.",
      },
      {
        value: "well_architected",
        label: "Azure Well-Architected",
        desc: "Security pillar review — defense in depth, least privilege, network segmentation best practices.",
      },
      {
        value: "remediation_priority",
        label: "Quick Wins",
        desc: "Surface highest-impact findings by exploitability × blast radius × remediation effort.",
      },
    ],
  },
  {
    group: "Network Behavioral Views",
    items: [
      {
        value: "traffic_flow",
        label: "Traffic Flow Analysis",
        desc: "East-west flows, north-south egress paths, bypassed inspection, unencrypted protocols, asymmetric inspection.",
      },
      {
        value: "dependency_chains",
        label: "Dependency Chains",
        desc: "Single points of failure, circular routing, shared service dependencies (DNS, NTP, AD), redundancy gaps.",
      },
      {
        value: "interconnect",
        label: "Interconnect Behavior",
        desc: "VNet peering configs, VPN/ER connectivity, vWAN hub routing, cross-tenant risks, route leaking.",
      },
      {
        value: "routing_decisions",
        label: "Routing Decisions",
        desc: "UDR overrides, BGP route scope, next-hop safety (NVA vs. Firewall vs. Internet), black-holes, prefix leaks.",
      },
      {
        value: "resilience",
        label: "Resilience Assumptions",
        desc: "Zone redundancy, active/active HA, health probe coverage, DDoS protection, SLA-breaking single points of failure.",
      },
    ],
  },
];

const CARD_BASE =
  "flex cursor-pointer items-start gap-3 rounded-xl border border-navy-700 bg-navy-50 dark:bg-navy-800/30 p-3 transition-colors hover:border-teal-600/60 hover:bg-teal-50 dark:hover:bg-teal-900/20";
const CARD_CHECKED =
  "has-[:checked]:border-teal-500 has-[:checked]:bg-teal-50 dark:bg-teal-900/30";

export function AiAnalysisForm({ engagementId }: { engagementId: string }) {
  const [state, action] = useActionState(runAnalysis, null);
  const [allState, allAction] = useActionState(runAllAnalysis, null);

  return (
    <div className="space-y-5">
      {/* ── Single focus form ── */}
      <form action={action} className="space-y-4">
        <input type="hidden" name="engagementId" value={engagementId} />

        {state?.error && (
          <p className="rounded-xl border border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-600 dark:text-red-400">
            {state.error}
          </p>
        )}
        {state?.success && (
          <p className="rounded-xl border border-teal-800 bg-teal-50 dark:bg-teal-900/20 px-4 py-3 text-sm text-teal-700 dark:text-teal-300">
            Analysis complete —{" "}
            <strong className="text-teal-800 dark:text-teal-200">{state.count}</strong> new finding
            {state.count !== 1 ? "s" : ""} generated.
          </p>
        )}

        <div className="space-y-4">
          {ANALYSIS_OPTIONS.map((group) => (
            <fieldset key={group.group}>
              <legend className="label-caps mb-2 block text-navy-500">{group.group}</legend>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {group.items.map((opt, i) => (
                  <label key={opt.value} className={`${CARD_BASE} ${CARD_CHECKED}`}>
                    <input
                      type="radio"
                      name="focus"
                      value={opt.value}
                      defaultChecked={i === 0 && group.group === "Security Frameworks"}
                      className="mt-0.5 accent-teal-500"
                    />
                    <div>
                      <p className="text-xs font-semibold text-navy-800 dark:text-navy-100">{opt.label}</p>
                      <p className="mt-0.5 text-xs text-navy-400">{opt.desc}</p>
                    </div>
                  </label>
                ))}
              </div>
            </fieldset>
          ))}
        </div>

        <p className="text-xs text-navy-500">
          Analysis uses live topology data, uploaded documents, and existing findings as
          context. Duplicate findings are not re-created.
        </p>

        <div className="flex items-center justify-end gap-3">
          <SubmitButton
            loadingText="Analyzing…"
            className="bg-teal-700 hover:bg-teal-600 focus:ring-teal-500"
          >
            Run AI analysis
          </SubmitButton>
        </div>
      </form>

      {/* ── Run All Analysis form ── */}
      <div className="border-t border-navy-700/40 pt-4">
        <form action={allAction}>
          <input type="hidden" name="engagementId" value={engagementId} />

          {allState?.error && (
            <p className="mb-3 rounded-xl border border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-600 dark:text-red-400">
              {allState.error}
            </p>
          )}
          {allState?.success && (
            <p className="mb-3 rounded-xl border border-teal-800 bg-teal-50 dark:bg-teal-900/20 px-4 py-3 text-sm text-teal-700 dark:text-teal-300">
              All analyses complete —{" "}
              <strong className="text-teal-800 dark:text-teal-200">{allState.count}</strong> unique new
              finding{allState.count !== 1 ? "s" : ""} generated across all 11 focus types.
            </p>
          )}

          <div className="flex items-center justify-between gap-4 rounded-xl border border-navy-700/40 bg-navy-50 dark:bg-navy-800/20 px-4 py-3">
            <div>
              <p className="text-xs font-semibold text-navy-500 dark:text-navy-200">Run All Analysis</p>
              <p className="mt-0.5 text-xs text-navy-500">
                Runs all 11 focus types in parallel. May take a few minutes.
              </p>
            </div>
            <SubmitButton
              loadingText="Running all…"
              className="shrink-0 bg-navy-700 hover:bg-navy-600 focus:ring-navy-500"
            >
              Run all analysis
            </SubmitButton>
          </div>
        </form>
      </div>
    </div>
  );
}
