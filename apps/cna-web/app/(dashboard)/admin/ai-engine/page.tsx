import Link from "next/link";

import { setAiEngineAction } from "@/app/(dashboard)/admin/ai-engine/actions";
import { auth } from "@/lib/auth";
import { getAiEngineDashboardState } from "@/lib/ai-engine";

function StatusPill({ active, configured }: { active?: boolean; configured?: boolean }) {
  const label = active ? "Active" : configured ? "Available" : "Unavailable";
  const styles = active
    ? "border-teal-300 bg-teal-50 text-teal-700"
    : configured
      ? "border-blue-200 bg-blue-50 text-blue-700"
      : "border-amber-200 bg-amber-50 text-amber-700";

  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${styles}`}>
      {label}
    </span>
  );
}

export default async function AiEnginePage() {
  const [session, state] = await Promise.all([auth(), getAiEngineDashboardState()]);
  const isAdmin = session?.user.role === "ADMIN";

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-white/70 bg-white/80 p-6 shadow-sm backdrop-blur dark:border-navy-700 dark:bg-navy-900/70">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <Link
              href="/dashboard"
              className="text-sm font-semibold text-blue-700 hover:text-blue-900 dark:text-blue-300"
            >
              &larr; Dashboard
            </Link>
            <h1 className="mt-4 text-3xl font-bold tracking-tight text-navy-900 dark:text-white">
              AI Engine
            </h1>
            <p className="mt-2 max-w-3xl text-sm text-navy-500 dark:text-navy-300">
              Validate the active GenAI provider (Azure OpenAI) and the MCP server
              endpoints used by the assessment app.
            </p>
          </div>
          <div className="rounded-xl border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-800">
            <div className="text-xs font-semibold uppercase tracking-[0.16em]">Global default</div>
            <div className="mt-1 font-bold">{state.defaultEngine}</div>
          </div>
        </div>
      </div>

      <section className="grid gap-4 lg:grid-cols-2">
        {state.engines.map((engine) => (
          <article
            key={engine.id}
            className="rounded-2xl border border-white/70 bg-white p-6 shadow-sm dark:border-navy-700 dark:bg-navy-900"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-xl font-bold text-navy-900 dark:text-white">{engine.label}</h2>
                <p className="mt-1 text-sm text-navy-500 dark:text-navy-300">
                  {engine.description}
                </p>
              </div>
              <StatusPill active={engine.active} configured={engine.configured} />
            </div>

            <dl className="mt-6 space-y-3">
              {engine.details.map((detail) => (
                <div key={detail.label} className="flex justify-between gap-4 border-b border-navy-50 pb-2 text-sm last:border-b-0 dark:border-navy-800">
                  <dt className="font-semibold text-navy-500 dark:text-navy-300">{detail.label}</dt>
                  <dd className="max-w-[60%] truncate text-right font-mono text-xs text-navy-800 dark:text-navy-100">
                    {detail.value}
                  </dd>
                </div>
              ))}
            </dl>

            {!engine.configured && (
              <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                Missing Terraform/env config: {engine.missing.join(", ")}
              </div>
            )}

            <form action={setAiEngineAction} className="mt-6">
              <input type="hidden" name="engine" value={engine.id} />
              <button
                type="submit"
                disabled={!isAdmin || engine.active || !engine.configured}
                className="rounded-lg bg-navy-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-navy-700 disabled:cursor-not-allowed disabled:bg-navy-200 disabled:text-navy-500 dark:bg-teal-500 dark:text-navy-950 dark:hover:bg-teal-400 dark:disabled:bg-navy-700 dark:disabled:text-navy-400"
              >
                {engine.active ? "Current engine" : "Set as active"}
              </button>
            </form>
          </article>
        ))}
      </section>

      <section className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900 shadow-sm dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-100">
        <h2 className="font-bold">Deployment validation</h2>
        <p className="mt-2">
          Azure OpenAI is the Terraform-managed GenAI provider: a private endpoint into
          the CNA VNet, RBAC via the app&apos;s managed identity, the model deployment, and
          the app environment variables are all provisioned by Terraform.
        </p>
        <p className="mt-2">
          Operators should confirm the Azure OpenAI host resolves through the private
          endpoint from inside the VNet and that managed-identity inference succeeds (no
          API-key fallback — local auth is disabled on the account).
        </p>
      </section>

      <section className="rounded-2xl border border-white/70 bg-white p-6 shadow-sm dark:border-navy-700 dark:bg-navy-900">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-xl font-bold text-navy-900 dark:text-white">MCP Servers</h2>
            <p className="text-sm text-navy-500 dark:text-navy-300">
              These values are injected by Terraform and surfaced here for validation.
            </p>
          </div>
          {!isAdmin && (
            <span className="rounded-full border border-navy-200 px-3 py-1 text-xs font-semibold text-navy-500">
              View only
            </span>
          )}
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-3">
          {state.mcpServers.map((server) => (
            <div
              key={server.id}
              className="rounded-xl border border-navy-100 bg-navy-50/60 p-4 dark:border-navy-800 dark:bg-navy-950/60"
            >
              <div className="flex items-center justify-between gap-3">
                <h3 className="font-bold text-navy-900 dark:text-white">{server.label}</h3>
                <StatusPill configured={server.configured} />
              </div>
              <div className="mt-4 space-y-2 text-sm">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-navy-400">
                    Transport
                  </div>
                  <div className="font-mono text-xs text-navy-800 dark:text-navy-100">
                    {server.transport}
                  </div>
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-navy-400">
                    Endpoint
                  </div>
                  <div className="truncate font-mono text-xs text-navy-800 dark:text-navy-100">
                    {server.endpoint}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
