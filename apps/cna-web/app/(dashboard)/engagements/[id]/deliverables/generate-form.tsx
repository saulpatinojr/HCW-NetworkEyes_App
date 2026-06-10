"use client";

import { useActionState, useRef } from "react";
import { generateDeliverable, generateAllAssessments } from "./actions";
import { SubmitButton } from "@/components/ui/submit-button";

const ASSESSMENT_TYPES = [
  {
    value: "COMPREHENSIVE_ASSESSMENT",
    label: "Comprehensive Assessment",
    audience: "All Stakeholders",
    desc: "Full report covering architecture, security, compliance, and resilience — all findings included. Opens as a web page; print to PDF.",
    icon: "M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  },
  {
    value: "EXECUTIVE_SUMMARY",
    label: "Executive Summary",
    audience: "CxO / CISO / Board",
    desc: "All risks in business language — impact per finding, severity breakdown, 30/60/90-day action roadmap.",
    icon: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
  },
  {
    value: "TECHNICAL_FINDINGS",
    label: "Technical Findings",
    audience: "Security Engineers / Architects",
    desc: "Every finding with root cause, Azure CLI remediation steps, NIST/CIS control mapping, and MS Learn links.",
    icon: "M10 21h7a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v11m0 5l4.879-4.879m0 0a3 3 0 104.243-4.242 3 3 0 00-4.243 4.242z",
  },
  {
    value: "REMEDIATION_PLAN",
    label: "Remediation Plan",
    audience: "IT / Platform Team",
    desc: "Prioritized task list with numbered steps, validation checks, rollback procedures, and effort estimates.",
    icon: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4",
  },
  {
    value: "SPECIALIZATION_REPORT",
    label: "Specialization Report",
    audience: "Security Architect / Compliance",
    desc: "Framework gap analysis (NIST/CIS/WAF), maturity scoring, compliance gap register, and architecture recommendations.",
    icon: "M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z",
  },
  {
    value: "ENCYCLOPEDIA_CONDENSED",
    label: "Networking Encyclopedia — Condensed",
    audience: "Executive Sponsors",
    desc: "Executive edition of the 6-chapter encyclopedia: maturity radar, key stats, top findings, diagrams, and roadmap summary. Opens as a web page; print to PDF.",
    icon: "M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253",
  },
  {
    value: "ENCYCLOPEDIA_EXPANDED",
    label: "Networking Encyclopedia — Expanded",
    audience: "All Stakeholders",
    desc: "Full-density 6-chapter encyclopedia: East-West and North-South deep dives, FinOps cost matrix, resilience gaps, per-finding remediation playbooks, and future-state roadmap.",
    icon: "M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253",
  },
];

const CARD_BASE =
  "flex cursor-pointer items-start gap-3 rounded-xl border border-navy-700 bg-navy-800/30 p-3.5 transition-colors hover:border-teal-600/60 hover:bg-teal-900/20";
const CARD_CHECKED = "has-[:checked]:border-teal-500 has-[:checked]:bg-teal-900/30";

export function GenerateDeliverableForm({ engagementId }: { engagementId: string }) {
  const [state, action] = useActionState(generateDeliverable, null);
  const [allState, allAction] = useActionState(generateAllAssessments, null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function clientAction(formData: FormData) {
    const file = fileRef.current?.files?.[0];
    if (file) {
      const reader = new FileReader();
      const dataUrl = await new Promise<string>((resolve) => {
        reader.onload = () => resolve(reader.result as string);
        reader.readAsDataURL(file);
      });
      formData.set("customerLogoUrl", dataUrl);
    }
    return action(formData);
  }

  return (
    <div className="space-y-5">
      {/* ── Single assessment form ── */}
      <form action={clientAction} className="space-y-4">
        <input type="hidden" name="engagementId" value={engagementId} />

        {state?.error && (
          <p className="rounded-xl border border-red-800 bg-red-900/20 px-4 py-3 text-sm text-red-400">
            {state.error}
          </p>
        )}
        {state?.success && (
          <p className="rounded-xl border border-teal-800 bg-teal-900/20 px-4 py-3 text-sm text-teal-300">
            Assessment generated — scroll up to view it.
          </p>
        )}

        {/* Assessment type */}
        <div>
          <h3 className="label-caps mb-2 text-navy-500">Assessment Type</h3>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {ASSESSMENT_TYPES.map((opt, i) => (
              <label key={opt.value} className={`${CARD_BASE} ${CARD_CHECKED}`}>
                <input
                  type="radio"
                  name="type"
                  value={opt.value}
                  defaultChecked={i === 0}
                  className="mt-0.5 accent-teal-500"
                />
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <svg aria-hidden="true" focusable="false" className="h-3.5 w-3.5 shrink-0 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d={opt.icon} />
                    </svg>
                    <p className="text-xs font-semibold text-navy-100">{opt.label}</p>
                  </div>
                  <p className="mt-1 text-xs font-medium text-teal-500">{opt.audience}</p>
                  <p className="mt-0.5 text-xs text-navy-400">{opt.desc}</p>
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Customer logo */}
        <div>
          <h3 className="label-caps mb-1 text-navy-500">Customer Logo (optional)</h3>
          <p className="mb-2 text-xs text-navy-600">
            PNG or SVG — personalizes the report header. Leave blank to use the default logo.
          </p>
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/svg+xml"
            aria-label="Customer logo (PNG or SVG)"
            className="block w-full text-sm text-navy-500 file:mr-3 file:rounded-lg file:border-0 file:bg-teal-900/30 file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-teal-300 hover:file:bg-teal-900/50"
          />
        </div>

        <p className="text-xs text-navy-600">
          Title is auto-generated using the client org name, assessment type, date, and sequence number.
          Generation typically takes 20–60 seconds.
        </p>

        <div className="flex justify-end">
          <SubmitButton
            loadingText="Generating (this may take ~30s)…"
            className="bg-teal-700 hover:bg-teal-600 focus:ring-teal-500"
          >
            Generate assessment
          </SubmitButton>
        </div>
      </form>

      {/* ── Generate All form ── */}
      <div className="border-t border-navy-700/40 pt-4">
        <form action={allAction}>
          <input type="hidden" name="engagementId" value={engagementId} />

          {allState?.error && (
            <p className="mb-3 rounded-xl border border-red-800 bg-red-900/20 px-4 py-3 text-sm text-red-400">
              {allState.error}
            </p>
          )}
          {allState?.success && (
            <p className="mb-3 rounded-xl border border-teal-800 bg-teal-900/20 px-4 py-3 text-sm text-teal-300">
              All assessments generated —{" "}
              <strong className="text-teal-200">{allState.count}</strong> of 5 created successfully.
            </p>
          )}

          <div className="flex items-center justify-between gap-4 rounded-xl border border-navy-700/40 bg-navy-800/20 px-4 py-3">
            <div>
              <p className="text-xs font-semibold text-navy-200">Generate All Assessments</p>
              <p className="mt-0.5 text-xs text-navy-500">
                Runs all 5 types in parallel. Each is auto-named and saved. May take several minutes.
              </p>
            </div>
            <SubmitButton
              loadingText="Generating all…"
              className="shrink-0 bg-navy-700 hover:bg-navy-600 focus:ring-navy-500"
            >
              Generate all
            </SubmitButton>
          </div>
        </form>
      </div>
    </div>
  );
}
