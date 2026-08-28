"use client";

import { useActionState, useEffect, useRef, useState, useTransition } from "react";
import { z } from "zod";
import { useRouter } from "next/navigation";
import { startDiscovery, startAllDiscovery } from "../discovery/actions";
import { deleteCloudCredential } from "../cloud-credentials/actions";
import { StatusBadge } from "@/components/ui/status-badge";
import { SubmitButton } from "@/components/ui/submit-button";
import { summarizeErrorText } from "@/lib/summarize-error";
import type { CloudCredential, DiscoveryJob } from "@prisma/client";

// ─── Types ────────────────────────────────────────────────────────────────────

type TopologySummary = {
  vnets: number;
  subnets: number;
  firewalls: number;
  appGateways: number;
  dnsZones: number;
  expressRoutes: number;
  workload?: { vmCount: number; acaCount: number; aksCount: number; fnCount: number };
  bgp?: { gatewaysWithBgp: number; peersConnected: number; peersDisconnected: number; routesLearned: number };
  observability?: { networkWatchers: number; logWorkspaces: number; nsgFlowLogsEnabled: number; nsgTotal: number };
  metricsCollected?: boolean;
};

type SeverityCount = { severity: string; count: number };

type JobSummary = Pick<
  DiscoveryJob,
  | "id"
  | "status"
  | "startedAt"
  | "completedAt"
  | "findingsCount"
  | "errorMessage"
  | "progressLog"
  | "credentialId"
> & {
  topologySummary?: TopologySummary | null;
  findingsBySeverity?: SeverityCount[];
};

const ACTIVE_STATUSES = new Set(["QUEUED", "RUNNING"]);
const POLL_INTERVAL_MS = 3000;

const styleKey = "style";
const makeStyle = (props: React.CSSProperties) => ({ [styleKey]: props }) as any;

const SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"];
const SEVERITY_STYLE: Record<string, string> = {
  CRITICAL: "bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400",
  HIGH: "bg-orange-50 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400",
  MEDIUM: "bg-yellow-50 dark:bg-yellow-900/30 text-yellow-600 dark:text-yellow-400",
  LOW: "bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400",
  INFORMATIONAL: "bg-navy-100/60 dark:bg-navy-700/40 text-navy-400 dark:text-navy-300",
};

// ─── Inline job entry (inside collapsible) ────────────────────────────────────

function JobEntry({
  initial,
  onUpdate,
}: {
  initial: JobSummary;
  onUpdate?: (job: JobSummary) => void;
}) {
  const [job, setJob] = useState(initial);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!ACTIVE_STATUSES.has(job.status)) return;
    function poll() {
      fetch(`/api/discovery-jobs/${job.id}`)
        .then((r) => r.json())
        .then((data: JobSummary) => {
          setJob(data);
          onUpdate?.(data);
          if (ACTIVE_STATUSES.has(data.status)) {
            timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
          }
        })
        .catch(() => {
          timerRef.current = setTimeout(poll, POLL_INTERVAL_MS * 2);
        });
    }
    timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.id, job.status]);

  // OWA-10: Schema check — parse JSON and validate with Zod (array of strings)
  const progress: string[] = (() => {
    if (!job.progressLog) return [];
    try {
      const parsed = JSON.parse(job.progressLog);
      const safeLog = z.array(z.string()).safeParse(parsed);
      if (safeLog.success) {
        return safeLog.data;
      }
      return [String(job.progressLog)];
    } catch {
      return [job.progressLog];
    }
  })();

  const isActive = ACTIVE_STATUSES.has(job.status);
  const isCompleted = job.status === "COMPLETED";
  const isFailed = job.status === "FAILED";

  const severityCounts = SEVERITY_ORDER.map((sev) => {
    const found = job.findingsBySeverity?.find((s) => s.severity === sev);
    return { severity: sev, count: found?.count ?? 0 };
  }).filter((s) => s.count > 0);

  return (
    <div className="rounded-lg border border-navy-700/40 bg-navy-50 dark:bg-navy-800/30 p-3">
      {/* Status + timestamp */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {isCompleted ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-teal-50 dark:bg-teal-900/40 px-2 py-0.5 text-xs font-semibold text-teal-700 dark:text-teal-400">
              ● Completed
            </span>
          ) : (
            <StatusBadge value={job.status} variant="job" />
          )}
          {isActive && (
            <>
              {/* WAI-19: Hide decorative spinner from screen readers, convey status with sr-only */}
              <svg aria-hidden="true" focusable="false" className="h-3.5 w-3.5 animate-spin text-blue-600 dark:text-blue-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span className="sr-only" aria-live="polite">Discovery run in progress...</span>
            </>
          )}
          {isCompleted && job.findingsCount != null && (
            <span className="rounded-full bg-blue-50 dark:bg-blue-900/30 px-2 py-0.5 text-xs font-semibold text-blue-600 dark:text-blue-400">
              {job.findingsCount} finding{job.findingsCount !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        <p className="text-xs text-navy-400">
          {job.startedAt
            ? new Date(job.startedAt).toLocaleString()
            : "Queued"}
          {job.completedAt && ` → ${new Date(job.completedAt).toLocaleString()}`}
        </p>
      </div>

      {/* Error */}
      {isFailed && job.errorMessage && (
        <div className="mt-2 rounded border border-red-300/60 dark:border-red-800/40 bg-red-50 dark:bg-red-900/20 px-3 py-2 text-xs text-red-700 dark:text-red-400">
          {summarizeErrorText(job.errorMessage)}
        </div>
      )}

      {/* Severity counts */}
      {isCompleted && severityCounts.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {severityCounts.map(({ severity, count }) => (
            <span
              key={severity}
              className={`rounded-full px-2 py-0.5 text-xs font-semibold ${SEVERITY_STYLE[severity] ?? "bg-navy-100/60 dark:bg-navy-700/40 text-navy-400 dark:text-navy-300"}`}
            >
              {severity}: {count}
            </span>
          ))}
        </div>
      )}

      {/* Topology summary */}
      {isCompleted && job.topologySummary && (
        <div className="mt-2 space-y-2">
          {/* Network resources row */}
          <div className="flex flex-wrap gap-1.5">
            {[
              { label: "VNets", value: job.topologySummary.vnets },
              { label: "Subnets", value: job.topologySummary.subnets },
              { label: "Firewalls", value: job.topologySummary.firewalls },
              { label: "AppGWs", value: job.topologySummary.appGateways },
              { label: "DNS Zones", value: job.topologySummary.dnsZones },
              { label: "ExpressRoute", value: job.topologySummary.expressRoutes },
            ].filter(({ value }) => value > 0).map(({ label, value }) => (
              <div key={label} className="flex items-center gap-1 rounded border border-navy-700/40 bg-navy-100/60 dark:bg-navy-800/50 px-2 py-1">
                <span className="text-sm font-bold text-navy-800 dark:text-navy-100">{value}</span>
                <span className="text-xs text-navy-400">{label}</span>
              </div>
            ))}
          </div>

          {/* Workload inventory row */}
          {job.topologySummary.workload && (
            <div className="rounded border border-navy-700/30 bg-navy-50 dark:bg-navy-900/30 px-2.5 py-1.5">
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-navy-500">Workload Inventory</p>
              <div className="flex flex-wrap gap-1.5">
                {[
                  { label: "VMs", value: job.topologySummary.workload.vmCount },
                  { label: "ACA", value: job.topologySummary.workload.acaCount },
                  { label: "AKS", value: job.topologySummary.workload.aksCount },
                  { label: "Functions", value: job.topologySummary.workload.fnCount },
                ].map(({ label, value }) => (
                  <div key={label} className="flex items-center gap-1 rounded border border-navy-700/40 bg-navy-100/60 dark:bg-navy-800/50 px-2 py-0.5">
                    <span className="text-xs font-bold text-navy-800 dark:text-navy-100">{value}</span>
                    <span className="text-[11px] text-navy-400">{label}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* BGP row */}
          {job.topologySummary.bgp && job.topologySummary.bgp.gatewaysWithBgp > 0 && (
            <div className="rounded border border-navy-700/30 bg-navy-50 dark:bg-navy-900/30 px-2.5 py-1.5">
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-navy-500">BGP & Routing</p>
              <div className="flex flex-wrap gap-1.5">
                <div className="flex items-center gap-1 rounded border border-navy-700/40 bg-navy-100/60 dark:bg-navy-800/50 px-2 py-0.5">
                  <span className="text-xs font-bold text-navy-800 dark:text-navy-100">{job.topologySummary.bgp.gatewaysWithBgp}</span>
                  <span className="text-[11px] text-navy-400">BGP GW</span>
                </div>
                {job.topologySummary.bgp.peersConnected > 0 && (
                  <div className="flex items-center gap-1 rounded border border-teal-700/40 bg-teal-50 dark:bg-teal-900/20 px-2 py-0.5">
                    <span className="text-xs font-bold text-teal-700 dark:text-teal-300">{job.topologySummary.bgp.peersConnected}</span>
                    <span className="text-[11px] text-teal-700 dark:text-teal-400">peers up</span>
                  </div>
                )}
                {job.topologySummary.bgp.peersDisconnected > 0 && (
                  <div className="flex items-center gap-1 rounded border border-red-700/40 bg-red-50 dark:bg-red-900/20 px-2 py-0.5">
                    <span className="text-xs font-bold text-red-700 dark:text-red-300">{job.topologySummary.bgp.peersDisconnected}</span>
                    <span className="text-[11px] text-red-600 dark:text-red-400">peers down</span>
                  </div>
                )}
                <div className="flex items-center gap-1 rounded border border-navy-700/40 bg-navy-100/60 dark:bg-navy-800/50 px-2 py-0.5">
                  <span className="text-xs font-bold text-navy-800 dark:text-navy-100">{job.topologySummary.bgp.routesLearned}</span>
                  <span className="text-[11px] text-navy-400">routes learned</span>
                </div>
              </div>
            </div>
          )}

          {/* Observability row */}
          {job.topologySummary.observability && (
            <div className="rounded border border-navy-700/30 bg-navy-50 dark:bg-navy-900/30 px-2.5 py-1.5">
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-navy-500">Observability</p>
              <div className="flex flex-wrap gap-1.5">
                <div className="flex items-center gap-1 rounded border border-navy-700/40 bg-navy-100/60 dark:bg-navy-800/50 px-2 py-0.5">
                  <span className="text-xs font-bold text-navy-800 dark:text-navy-100">{job.topologySummary.observability.networkWatchers}</span>
                  <span className="text-[11px] text-navy-400">NW regions</span>
                </div>
                <div className="flex items-center gap-1 rounded border border-navy-700/40 bg-navy-100/60 dark:bg-navy-800/50 px-2 py-0.5">
                  <span className="text-xs font-bold text-navy-800 dark:text-navy-100">{job.topologySummary.observability.logWorkspaces}</span>
                  <span className="text-[11px] text-navy-400">Log workspaces</span>
                </div>
                {job.topologySummary.observability.nsgTotal > 0 && (
                  <div className={[
                    "flex items-center gap-1 rounded border px-2 py-0.5",
                    job.topologySummary.observability.nsgFlowLogsEnabled >= job.topologySummary.observability.nsgTotal
                      ? "border-teal-700/40 bg-teal-50 dark:bg-teal-900/20"
                      : "border-amber-700/40 bg-amber-50 dark:bg-amber-900/20",
                  ].join(" ")}>
                    <span className={`text-xs font-bold ${
                      job.topologySummary.observability.nsgFlowLogsEnabled >= job.topologySummary.observability.nsgTotal
                        ? "text-teal-700 dark:text-teal-300" : "text-amber-700 dark:text-amber-300"
                    }`}>
                      {job.topologySummary.observability.nsgFlowLogsEnabled}/{job.topologySummary.observability.nsgTotal}
                    </span>
                    <span className={`text-[11px] ${
                      job.topologySummary.observability.nsgFlowLogsEnabled >= job.topologySummary.observability.nsgTotal
                        ? "text-teal-700 dark:text-teal-400" : "text-amber-600 dark:text-amber-400"
                    }`}>NSG flow logs</span>
                  </div>
                )}
                {job.topologySummary.metricsCollected && (
                  <div className="flex items-center gap-1 rounded border border-blue-700/40 bg-blue-50 dark:bg-blue-900/20 px-2 py-0.5">
                    <span className="text-[11px] text-blue-700 dark:text-blue-300">metrics collected</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Progress log */}
      {progress.length > 0 && (
        <div className="mt-2 max-h-36 overflow-y-auto rounded border border-navy-700/40 bg-navy-100/60 dark:bg-navy-900/60 p-2 font-mono text-xs text-navy-400 dark:text-navy-300">
          {progress.map((line, i) => (
            <div
              key={i}
              className={i === progress.length - 1 && isActive ? "font-semibold text-teal-700 dark:text-teal-400" : ""}
            >
              {line}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Start / Re-sync Discovery form ───────────────────────────────────────────

function StartDiscoveryForm({
  engagementId,
  credentialId,
  hasCompleted,
}: {
  engagementId: string;
  credentialId: string;
  hasCompleted: boolean;
}) {
  const [state, action] = useActionState(startDiscovery, null);
  return (
    <form action={action} className="inline-flex flex-col items-start gap-1">
      <input type="hidden" name="engagementId" value={engagementId} />
      <input type="hidden" name="credentialId" value={credentialId} />
      {state?.error && (
        <span className="text-xs text-red-600 dark:text-red-400">{state.error}</span>
      )}
      {hasCompleted ? (
        <SubmitButton
          loadingText="Syncing…"
          className="!bg-teal-700 hover:!bg-teal-600 focus:!ring-teal-500"
        >
          ↺ Re-sync data
        </SubmitButton>
      ) : (
        <SubmitButton loadingText="Starting…">Start discovery</SubmitButton>
      )}
    </form>
  );
}

// ─── Delete credential form ────────────────────────────────────────────────────

function DeleteCredentialButton({
  credentialId,
  engagementId,
  label,
}: {
  credentialId: string;
  engagementId: string;
  label: string;
}) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [state, action, isPending] = useActionState(deleteCloudCredential, null);

  // After a successful delete, refresh the page via a normal GET instead of
  // triggering an RSC re-render from within the server action (which caused 500s).
  useEffect(() => {
    if (state?.deleted) router.refresh();
  }, [state, router]);

  if (confirming) {
    return (
      <form action={action} className="inline-flex flex-col items-start gap-1">
        <input type="hidden" name="credentialId" value={credentialId} />
        <input type="hidden" name="engagementId" value={engagementId} />
        {state?.error && (
          <span className="text-xs text-red-600 dark:text-red-400">{state.error}</span>
        )}
        <div className="inline-flex items-center gap-1.5">
          <span className="text-xs text-navy-400">Remove {label}?</span>
          <button
            type="submit"
            disabled={isPending}
            className="rounded bg-red-50 dark:bg-red-900/40 px-2 py-0.5 text-xs font-semibold text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/60 disabled:opacity-50"
          >
            {isPending ? "Removing…" : "Confirm"}
          </button>
          <button
            type="button"
            onClick={() => setConfirming(false)}
            disabled={isPending}
            className="rounded bg-navy-100/60 dark:bg-navy-700/40 px-2 py-0.5 text-xs text-navy-400 hover:bg-navy-100/60 dark:hover:bg-navy-700/60 disabled:opacity-50"
          >
            Cancel
          </button>
        </div>
      </form>
    );
  }

  return (
    <button
      type="button"
      onClick={() => setConfirming(true)}
      className="mt-1 inline-flex items-center gap-1 rounded border border-red-800/40 px-2 py-0.5 text-xs font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
    >
      <span>✕</span>
      <span>Remove</span>
    </button>
  );
}

interface ConnectionsPanelProps {
  engagementId: string;
  credentials: Pick<
    CloudCredential,
    "id" | "label" | "platform" | "tenantId" | "subscriptionIds" | "awsRoleArn" | "awsRegions"
  >[];
  jobs: JobSummary[];
}

// ─── Per-credential card (manages live job state) ─────────────────────────────

function CredentialCard({
  cred,
  initialJobs,
  engagementId,
}: {
  cred: ConnectionsPanelProps["credentials"][number];
  initialJobs: JobSummary[];
  engagementId: string;
}) {
  const [runsOpen, setRunsOpen] = useState(false);
  // Live job map: starts from server-rendered data, updated by polling.
  const [liveJobMap, setLiveJobMap] = useState<Map<string, JobSummary>>(
    () => new Map(initialJobs.map((j) => [j.id, j])),
  );

  const liveJobs = initialJobs.map((j) => liveJobMap.get(j.id) ?? j);
  const latestJob = liveJobs[0];
  const isActive = liveJobs.some((j) => ACTIVE_STATUSES.has(j.status));
  const hasCompleted = liveJobs.some((j) => j.status === "COMPLETED");

  // Poll the latest active job at the card level — independent of whether the
  // <details> runs list is open. This keeps the spinner + button state live.
  const activeJobId = liveJobs.find((j) => ACTIVE_STATUSES.has(j.status))?.id;
  const cardTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!activeJobId) return;
    function poll() {
      fetch(`/api/discovery-jobs/${activeJobId}`)
        .then((r) => r.json())
        .then((data: JobSummary) => {
          setLiveJobMap((prev) => new Map(prev).set(data.id, data));
          if (ACTIVE_STATUSES.has(data.status)) {
            cardTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
          }
        })
        .catch(() => {
          cardTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS * 2);
        });
    }
    cardTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
    return () => {
      if (cardTimerRef.current) clearTimeout(cardTimerRef.current);
    };
  }, [activeJobId]);

  function handleJobUpdate(updated: JobSummary) {
    setLiveJobMap((prev) => new Map(prev).set(updated.id, updated));
  }

  return (
    <div className="rounded-xl border border-navy-700/40 bg-navy-50 dark:bg-navy-800/20 p-4">
      {/* Credential header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold text-navy-800 dark:text-navy-100">{cred.label}</p>
            {isActive && (
              <svg className="h-3.5 w-3.5 animate-spin text-blue-600 dark:text-blue-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            )}
          </div>
          <p className="text-xs text-navy-400">
            {cred.platform === "AWS" ? (
              <>
                AWS · Role: {cred.awsRoleArn?.split("/").pop() ?? "—"}
                {cred.awsRegions.length > 0
                  ? ` · ${cred.awsRegions.length} region(s)`
                  : " · All enabled regions"}
              </>
            ) : (
              <>
                {cred.platform} · Tenant: {cred.tenantId?.slice(0, 8)}…
                {cred.subscriptionIds.length > 0
                  ? ` · ${cred.subscriptionIds.length} subscription(s)`
                  : " · All subscriptions"}
              </>
            )}
          </p>

          {/* Active job progress bar */}
          {isActive && (() => {
            const activeJob = liveJobs.find((j) => ACTIVE_STATUSES.has(j.status));
            // OWA-10: Schema check — parse JSON and validate with Zod (array of strings)
            const steps: string[] = (() => {
              if (!activeJob?.progressLog) return [];
              try {
                const parsed = JSON.parse(activeJob.progressLog);
                const safeLog = z.array(z.string()).safeParse(parsed);
                if (safeLog.success) {
                  return safeLog.data;
                }
                return [String(activeJob.progressLog)];
              } catch {
                return [activeJob.progressLog];
              }
            })();
            const ESTIMATED_STEPS = 28;
            const pct = steps.length === 0 ? 8 : Math.min(94, Math.round((steps.length / ESTIMATED_STEPS) * 100));
            const lastStep = steps[steps.length - 1] ?? (activeJob?.status === "QUEUED" ? "Queued — waiting to start…" : "Starting…");
            return (
              <div className="mt-2 space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-xs text-navy-400">{lastStep}</p>
                  <span className="shrink-0 text-xs font-semibold text-navy-400">{pct}%</span>
                </div>
                {/* WAI-11: progressbar role and values */}
                <div
                  role="progressbar"
                  {...{
                    "aria-valuenow": pct,
                    "aria-valuemin": 0,
                    "aria-valuemax": 100,
                  }}
                  aria-label={`Discovery progress: ${pct}%`}
                  className="h-1.5 w-full overflow-hidden rounded-full bg-navy-100/60 dark:bg-navy-700/50"
                >
                  <div
                    className="h-full rounded-full bg-teal-500 transition-all duration-700"
                    {...makeStyle({ width: `${pct}%` })}
                  />
                </div>
              </div>
            );
          })()}

          {/* Last run + collapsible toggle */}
          {/* WAI-12: Improve keyboard accessibility & focus indicator */}
          {liveJobs.length > 0 && (
            <details
              className="mt-1 group/runs"
              onToggle={(e) => setRunsOpen((e.target as HTMLDetailsElement).open)}
            >
              <summary
                {...{ "aria-expanded": runsOpen }}
                className="inline-flex cursor-pointer list-none items-center gap-1 text-xs text-navy-400 hover:text-navy-500 dark:hover:text-navy-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-1 rounded-sm"
              >
                <svg
                  aria-hidden="true"
                  focusable="false"
                  className="h-3 w-3 transition-transform group-open/runs:rotate-90"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2.5}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
                {liveJobs.length} run{liveJobs.length !== 1 ? "s" : ""} ·{" "}
                Last:{" "}
                {latestJob.status === "COMPLETED" ? (
                  <>
                    Completed {new Date(latestJob.completedAt!).toLocaleDateString()}
                    {latestJob.completedAt &&
                      Date.now() - new Date(latestJob.completedAt).getTime() < 60_000 && (
                        <span className="ml-1.5 inline-flex items-center rounded-full bg-teal-50 dark:bg-teal-900/40 px-1.5 py-0.5 text-[10px] font-semibold text-teal-700 dark:text-teal-400">
                          ✓ Just completed
                        </span>
                      )}
                  </>
                ) : latestJob.status === "FAILED" ? (
                  "Failed"
                ) : (
                  latestJob.status
                )}
              </summary>
              <div className="mt-2 space-y-2">
                {liveJobs.map((job) => (
                  <JobEntry key={job.id} initial={job} onUpdate={handleJobUpdate} />
                ))}
              </div>
            </details>
          )}
          {liveJobs.length === 0 && (
            <p className="mt-1 text-xs text-navy-500">No runs yet</p>
          )}
        </div>

        {/* Actions column */}
        <div className="flex flex-col items-end gap-1 shrink-0">
          <StartDiscoveryForm
            engagementId={engagementId}
            credentialId={cred.id}
            hasCompleted={hasCompleted}
          />
          <DeleteCredentialButton
            credentialId={cred.id}
            engagementId={engagementId}
            label={cred.label}
          />
        </div>
      </div>
    </div>
  );
}

// ─── Bulk discover / re-sync button ──────────────────────────────────────────

function BulkDiscoverButton({
  engagementId,
  allHaveRun,
  noneHaveRun,
  anyActive,
}: {
  engagementId: string;
  allHaveRun: boolean;
  noneHaveRun: boolean;
  anyActive: boolean;
}) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const canRun = allHaveRun || noneHaveRun;
  const label = allHaveRun ? "↺ Re-sync all data" : "▶ Discover all";
  const loadingLabel = allHaveRun ? "Queuing re-sync…" : "Queuing discovery…";

  const activeStyle = allHaveRun
    ? "bg-teal-700 hover:bg-teal-600 focus:ring-teal-500 text-white"
    : "bg-blue-700 hover:bg-blue-600 focus:ring-blue-500 text-white";
  const disabledStyle =
    "bg-navy-100/60 dark:bg-navy-700/40 text-navy-500 cursor-not-allowed";

  function handleClick() {
    setError(null);
    startTransition(async () => {
      const result = await startAllDiscovery(engagementId);
      if (result.error) {
        setError(result.error);
      } else {
        router.refresh();
      }
    });
  }

  return (
    <div className="flex flex-col items-end gap-1 pt-1">
      {error && <span className="text-xs text-red-600 dark:text-red-400">{error}</span>}
      <button
        type="button"
        onClick={handleClick}
        disabled={!canRun || anyActive || isPending}
        title={
          anyActive
            ? "A discovery is already running"
            : !canRun
            ? "Some connections have never been run — start each individually first"
            : undefined
        }
        className={[
          "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-offset-1",
          canRun && !anyActive && !isPending ? activeStyle : disabledStyle,
        ].join(" ")}
      >
        {isPending ? loadingLabel : label}
      </button>
      {!canRun && !anyActive && (
        <p className="text-[10px] text-navy-500 max-w-[16rem] text-right">
          Run each connection individually at least once to unlock bulk actions.
        </p>
      )}
    </div>
  );
}

// ─── Main panel ───────────────────────────────────────────────────────────────

export function ConnectionsPanel({
  engagementId,
  credentials,
  jobs,
}: ConnectionsPanelProps) {
  // Group jobs by credential, maintaining descending order
  const jobsByCredential = new Map<string, JobSummary[]>();
  for (const job of jobs) {
    if (!job.credentialId) continue;
    const existing = jobsByCredential.get(job.credentialId) ?? [];
    existing.push(job);
    jobsByCredential.set(job.credentialId, existing);
  }

  const credentialsWithJobs = new Set(jobs.map((j) => j.credentialId).filter(Boolean));
  const allHaveRun =
    credentials.length > 0 && credentials.every((c) => credentialsWithJobs.has(c.id));
  const noneHaveRun =
    credentials.length > 0 && credentials.every((c) => !credentialsWithJobs.has(c.id));
  const anyActive = jobs.some((j) => ACTIVE_STATUSES.has(j.status));

  return (
    <div className="space-y-3">
      {credentials.length === 0 ? (
        <p className="text-sm text-navy-400">
          No connections yet. Add one in the section below.
        </p>
      ) : (
        <>
          {credentials.map((cred) => (
            <CredentialCard
              key={cred.id}
              cred={cred}
              initialJobs={jobsByCredential.get(cred.id) ?? []}
              engagementId={engagementId}
            />
          ))}
          <BulkDiscoverButton
            engagementId={engagementId}
            allHaveRun={allHaveRun}
            noneHaveRun={noneHaveRun}
            anyActive={anyActive}
          />
        </>
      )}
    </div>
  );
}
