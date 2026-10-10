import Link from "next/link";

import { setAiEngineAction } from "@/app/(dashboard)/admin/ai-engine/actions";
import { ByoKeyForm } from "@/app/(dashboard)/admin/ai-engine/byo-key-form";
import { getAiEngineDashboardState, type AiEngineStatus } from "@/lib/ai-engine";
import { BYO_ENGINES } from "@/lib/ai-engine-rules";
import { auth } from "@/lib/auth";

function StatusPill({ active, configured }: { active?: boolean; configured?: boolean }) {
  const label = active ? "Active" : configured ? "Available" : "Unavailable";
  const styles = active
    ? "border-teal-300 bg-teal-50 text-teal-700"
    : configured
      ? "border-navy-200 bg-navy-50 text-navy-700"
      : "border-amber-200 bg-amber-50 text-amber-700";

  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${styles}`}>
      {label}
    </span>
  );
}

function EngineDetails({ engine }: { engine: AiEngineStatus }) {
  return (
    <>
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
          Missing: {engine.missing.join(", ")}
        </div>
      )}
    </>
  );
}

function EngineCard({ engine, children }: { engine: AiEngineStatus; children?: React.ReactNode }) {
  return (
    <article
      key={engine.id}
      className="rounded-2xl border border-white/70 bg-white p-6 shadow-sm dark:border-navy-700 dark:bg-navy-900"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-navy-900 dark:text-white">{engine.label}</h2>
          <p className="mt-1 text-sm text-navy-500 dark:text-navy-300">{engine.description}</p>
        </div>
        <StatusPill active={engine.active} configured={engine.configured} />
      </div>
      <EngineDetails engine={engine} />
      {children}
    </article>
  );
}

const MODE_COPY = {
  saas: {
    title: "SaaS engine",
    blurb:
      "This appliance was deployed with ai_mode = saas: the cloud-native GenAI service is provisioned by Terraform and authenticated with the workload identity. Switch modes by redeploying with a different ai_mode.",
  },
  "byo-api": {
    title: "Bring-your-own API",
    blurb:
      "This appliance was deployed with ai_mode = byo-api: no cloud AI service is provisioned. Paste an Anthropic and/or OpenAI API key below — these are the only secrets entered in the app, stored encrypted in the database. With one key that provider is used automatically; with both, the toggle chooses.",
  },
} as const;

export default async function AiEnginePage() {
  const [session, state] = await Promise.all([auth(), getAiEngineDashboardState()]);
  const isAdmin = session?.user.role === "ADMIN";
  const isByo = state.mode === "byo-api";
  const copy = MODE_COPY[state.mode];

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
            <h1 className="mt-4 text-3xl font-bold tracking-tight text-navy-900 dark:text-white">
              AI Engine
            </h1>
            <p className="mt-2 max-w-3xl text-sm text-navy-500 dark:text-navy-300">{copy.blurb}</p>
          </div>
          <div className="flex flex-col gap-2 text-sm">
            <div className="rounded-xl border border-navy-200 bg-navy-50 px-4 py-3 text-navy-800 dark:border-navy-700 dark:bg-navy-950 dark:text-navy-100">
              <div className="text-xs font-semibold uppercase tracking-[0.16em]">Mode</div>
              <div className="mt-1 font-bold">
                {copy.title} · {state.cloud}
              </div>
            </div>
            <div className="rounded-xl border border-teal-200 bg-teal-50 px-4 py-3 text-teal-800">
              <div className="text-xs font-semibold uppercase tracking-[0.16em]">Active engine</div>
              <div className="mt-1 font-bold">{state.activeEngine ?? "none configured"}</div>
            </div>
          </div>
        </div>
      </div>

      {isByo ? (
        <>
          <section className="rounded-2xl border border-white/70 bg-white p-6 shadow-sm dark:border-navy-700 dark:bg-navy-900">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-xl font-bold text-navy-900 dark:text-white">Active provider</h2>
                <p className="text-sm text-navy-500 dark:text-navy-300">
                  {state.byoToggleEnabled
                    ? "Both keys are present — choose which provider answers."
                    : "Enabled once both an Anthropic and an OpenAI key are saved. With a single key, that provider is used automatically."}
                </p>
              </div>
              {!isAdmin && (
                <span className="rounded-full border border-navy-200 px-3 py-1 text-xs font-semibold text-navy-500">
                  View only
                </span>
              )}
            </div>

            <div
              role="radiogroup"
              aria-label="Active bring-your-own provider"
              aria-disabled={!state.byoToggleEnabled || !isAdmin}
              className="mt-5 inline-flex rounded-xl border border-navy-200 bg-navy-50 p-1 dark:border-navy-700 dark:bg-navy-950"
            >
              {state.engines.map((engine) => {
                const disabled = !isAdmin || !state.byoToggleEnabled || engine.active;
                return (
                  <form key={engine.id} action={setAiEngineAction}>
                    <input type="hidden" name="engine" value={engine.id} />
                    <button
                      type="submit"
                      role="radio"
                      aria-checked={engine.active}
                      disabled={disabled}
                      className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${
                        engine.active
                          ? "bg-navy-900 text-white dark:bg-teal-500 dark:text-navy-950"
                          : "text-navy-700 hover:bg-white dark:text-navy-100 dark:hover:bg-navy-800"
                      } disabled:cursor-not-allowed ${
                        engine.active ? "" : "disabled:text-navy-400 dark:disabled:text-navy-600"
                      }`}
                    >
                      {engine.label}
                    </button>
                  </form>
                );
              })}
            </div>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            {state.engines.map((engine) => (
              <EngineCard key={engine.id} engine={engine}>
                {BYO_ENGINES.includes(engine.id as (typeof BYO_ENGINES)[number]) && (
                  <ByoKeyForm
                    provider={engine.id as (typeof BYO_ENGINES)[number]}
                    label={engine.label}
                    configured={engine.configured}
                    isAdmin={isAdmin}
                  />
                )}
              </EngineCard>
            ))}
          </section>
        </>
      ) : (
        <>
          <section className="grid gap-4 lg:grid-cols-2">
            {state.engines.map((engine) => (
              <EngineCard key={engine.id} engine={engine}>
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
              </EngineCard>
            ))}
          </section>

          <section className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900 shadow-sm dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-100">
            <h2 className="font-bold">Deployment validation</h2>
            {state.cloud === "aws" ? (
              <p className="mt-2">
                Amazon Bedrock is the Terraform-managed GenAI provider: the task role&apos;s invoke
                policy, the inference profile, the bedrock-runtime VPC endpoint, and the app
                environment variables are all provisioned by Terraform. Operators should confirm
                model access is enabled for this account and region in the Bedrock console.
              </p>
            ) : (
              <>
                <p className="mt-2">
                  Azure OpenAI is the Terraform-managed GenAI provider: a private endpoint into the
                  CNA VNet, RBAC via the app&apos;s managed identity, the model deployment, and the
                  app environment variables are all provisioned by Terraform.
                </p>
                <p className="mt-2">
                  Operators should confirm the Azure OpenAI host resolves through the private
                  endpoint from inside the VNet and that managed-identity inference succeeds (no
                  API-key fallback — local auth is disabled on the account).
                </p>
              </>
            )}
          </section>
        </>
      )}

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
