import Link from "next/link";

import { checkImageUpdateAction } from "@/app/(dashboard)/admin/updates/actions";
import { auth } from "@/lib/auth";
import { getApplianceCloud } from "@/lib/ai-engine";
import { getImageUpdateState, type UpdateVerdict } from "@/lib/image-update";

const VERDICT_COPY: Record<UpdateVerdict, { label: string; styles: string }> = {
  "up-to-date": { label: "Up to date", styles: "border-teal-300 bg-teal-50 text-teal-700" },
  "update-available": { label: "Update available", styles: "border-amber-300 bg-amber-50 text-amber-800" },
  unknown: { label: "Unknown", styles: "border-navy-200 bg-navy-50 text-navy-700" },
};

function VerdictPill({ verdict }: { verdict: UpdateVerdict }) {
  const copy = VERDICT_COPY[verdict];
  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${copy.styles}`}>{copy.label}</span>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-navy-50 pb-2 text-sm last:border-b-0 dark:border-navy-800">
      <dt className="font-semibold text-navy-500 dark:text-navy-300">{label}</dt>
      <dd className="max-w-[60%] truncate text-right font-mono text-xs text-navy-800 dark:text-navy-100">
        {value || "—"}
      </dd>
    </div>
  );
}

function formatTimestamp(value: string): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toUTCString();
}

export default async function UpdatesPage() {
  const [session, state] = await Promise.all([auth(), getImageUpdateState()]);
  const isAdmin = session?.user.role === "ADMIN";
  const cloud = getApplianceCloud();
  const links = state.appliance;

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-white/70 bg-white/80 p-6 shadow-sm backdrop-blur dark:border-navy-700 dark:bg-navy-900/70">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <Link
              href="/dashboard"
              className="text-sm font-semibold text-teal-700 hover:text-teal-800 dark:text-teal-300"
            >
              &larr; Dashboard
            </Link>
            <h1 className="mt-4 text-3xl font-bold tracking-tight text-navy-900 dark:text-white">Updates</h1>
            <p className="mt-2 max-w-3xl text-sm text-navy-500 dark:text-navy-300">
              This deployment runs immutable images published by the core. The running build is compared
              with the newest build in the registry; updates are applied by the appliance&apos;s
              workflows, never by the containers themselves.
            </p>
          </div>
          <div className="flex flex-col items-end gap-3">
            <VerdictPill verdict={state.verdict} />
            <form action={checkImageUpdateAction}>
              <button
                type="submit"
                disabled={!isAdmin || !state.enabled}
                className="rounded-lg bg-navy-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-navy-700 disabled:cursor-not-allowed disabled:bg-navy-200 disabled:text-navy-500 dark:bg-teal-500 dark:text-navy-950 dark:hover:bg-teal-400 dark:disabled:bg-navy-700 dark:disabled:text-navy-400"
              >
                Check now
              </button>
            </form>
            {!isAdmin && (
              <span className="rounded-full border border-navy-200 px-3 py-1 text-xs font-semibold text-navy-500">
                View only
              </span>
            )}
          </div>
        </div>
      </div>

      <section className="grid gap-4 lg:grid-cols-2">
        <article className="rounded-2xl border border-white/70 bg-white p-6 shadow-sm dark:border-navy-700 dark:bg-navy-900">
          <h2 className="text-xl font-bold text-navy-900 dark:text-white">Running</h2>
          <p className="mt-1 text-sm text-navy-500 dark:text-navy-300">
            Identity baked into the image at build time and the reference the appliance deployed.
          </p>
          <dl className="mt-6 space-y-3">
            <Detail label="Build" value={state.running.shaTag} />
            <Detail label="Commit" value={state.running.buildSha} />
            <Detail label="Image" value={state.running.image} />
            <Detail label="Cloud" value={cloud} />
          </dl>
        </article>

        <article className="rounded-2xl border border-white/70 bg-white p-6 shadow-sm dark:border-navy-700 dark:bg-navy-900">
          <h2 className="text-xl font-bold text-navy-900 dark:text-white">Newest published</h2>
          <p className="mt-1 text-sm text-navy-500 dark:text-navy-300">
            Resolved from the registry&apos;s floating tag with the deployment&apos;s pull credential.
          </p>
          <dl className="mt-6 space-y-3">
            <Detail label="Build" value={state.published.shaTag} />
            <Detail label="Commit" value={state.published.revision} />
            <Detail label="Built" value={formatTimestamp(state.published.createdAt)} />
            <Detail label="Resolved tag" value={state.published.floatingTag} />
            <Detail
              label="Last checked"
              value={
                state.checkedAt
                  ? `${formatTimestamp(state.checkedAt)} (${state.source}, every ${state.intervalMinutes} min)`
                  : ""
              }
            />
          </dl>
          {state.error && (
            <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              {state.error}
            </div>
          )}
        </article>
      </section>

      <section className="rounded-2xl border border-white/70 bg-white p-6 shadow-sm dark:border-navy-700 dark:bg-navy-900">
        <h2 className="text-xl font-bold text-navy-900 dark:text-white">How an update is applied</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div className="rounded-xl border border-navy-100 bg-navy-50/60 p-4 dark:border-navy-800 dark:bg-navy-950/60">
            <h3 className="font-bold text-navy-900 dark:text-white">Automatic — dev</h3>
            <p className="mt-2 text-sm text-navy-600 dark:text-navy-200">
              The appliance&apos;s <span className="font-mono text-xs">230 · Image Update</span> workflow
              receives the core&apos;s publish notification and also polls every six hours. When dev is
              behind, it runs a full release through{" "}
              <span className="font-mono text-xs">210 · Deploy</span> with the recorded AI mode.
              Setting the repository variable <span className="font-mono text-xs">AUTO_UPDATE_DEV</span>{" "}
              to <span className="font-mono text-xs">false</span> freezes dev.
            </p>
            {links && (
              <a
                href={links.imageUpdateWorkflow}
                target="_blank"
                rel="noreferrer"
                className="mt-3 inline-block text-sm font-semibold text-teal-700 hover:text-teal-800 dark:text-teal-300"
              >
                Open 230 · Image Update &rarr;
              </a>
            )}
          </div>
          <div className="rounded-xl border border-navy-100 bg-navy-50/60 p-4 dark:border-navy-800 dark:bg-navy-950/60">
            <h3 className="font-bold text-navy-900 dark:text-white">Manual — prod</h3>
            <p className="mt-2 text-sm text-navy-600 dark:text-navy-200">
              Prod is human-gated. The same workflow opens an{" "}
              <span className="font-mono text-xs">update-available</span> issue with the exact image
              references; an operator runs <span className="font-mono text-xs">210 · Deploy</span> for
              prod with the recorded AI mode, and the approval gate applies.
            </p>
            {links && (
              <div className="mt-3 flex flex-wrap gap-4">
                <a
                  href={links.updateIssues}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm font-semibold text-teal-700 hover:text-teal-800 dark:text-teal-300"
                >
                  Open update requests &rarr;
                </a>
                <a
                  href={links.deployWorkflow}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm font-semibold text-teal-700 hover:text-teal-800 dark:text-teal-300"
                >
                  Run 210 · Deploy &rarr;
                </a>
              </div>
            )}
          </div>
        </div>
        {!links && (
          <p className="mt-4 text-sm text-navy-500 dark:text-navy-300">
            Set <span className="font-mono text-xs">CNA_APPLIANCE_REPO</span> (owner/repo) in the
            appliance&apos;s Terraform to link the workflows and update requests from here.
          </p>
        )}
      </section>
    </div>
  );
}
