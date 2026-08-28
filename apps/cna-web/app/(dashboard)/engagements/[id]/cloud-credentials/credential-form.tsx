"use client";

import { useState, useTransition, useRef } from "react";
import { addBulkCredentials, testAzureConnection } from "./actions";
import { SpHelpModal } from "@/components/ui/sp-help-modal";

type Platform = "AZURE" | "AWS";

interface Subscription {
  name: string;
  subscriptionId: string;
  tenantId?: string;
}

const GUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const isGuid = (s: string) => GUID_RE.test(s.trim());

function parseSubscriptionCsv(text: string): {
  subs: Subscription[];
  errors: string[];
} {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (!lines.length) return { subs: [], errors: ["CSV file is empty."] };

  const dataLines = lines[0].toLowerCase().includes("subscription")
    ? lines.slice(1)
    : lines;

  const errors: string[] = [];
  const subs: Subscription[] = [];

  for (let i = 0; i < dataLines.length; i++) {
    const cols = dataLines[i]
      .split(",")
      .map((c) => c.trim().replace(/^"|"$/g, ""));
    const [rawName = "", rawSubId = "", rawTenantId = ""] = cols;

    if (!rawName && !rawSubId) continue;

    if (!isGuid(rawSubId)) {
      errors.push(`Row ${i + 1}: "${rawSubId}" is not a valid subscription ID (expected GUID)`);
      continue;
    }
    if (rawTenantId && !isGuid(rawTenantId)) {
      errors.push(`Row ${i + 1}: "${rawTenantId}" is not a valid tenant ID (expected GUID)`);
      continue;
    }

    subs.push({
      name: rawName.trim() || rawSubId.trim(),
      subscriptionId: rawSubId.trim(),
      tenantId: rawTenantId.trim() || undefined,
    });
  }

  return { subs, errors };
}

function downloadTemplate() {
  const csv = [
    "subscription_name,subscription_id,tenant_id",
    "Production,xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx,xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "Staging,yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy,xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  ].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "subscription_import_template.csv";
  a.click();
  URL.revokeObjectURL(url);
}

const INPUT_CLS =
  "mt-1 block w-full rounded-lg border border-navy-600/50 bg-white/60 dark:bg-navy-800/60 px-3 py-2 text-sm text-navy-800 dark:text-navy-100 placeholder-navy-500 focus:border-teal-500 focus:outline-none focus:ring-1 focus:ring-teal-500";

export function CredentialForm({ engagementId }: { engagementId: string }) {
  const [platform, setPlatform] = useState<Platform>("AZURE");

  const [tenantId, setTenantId] = useState("");
  const [spClientId, setSpClientId] = useState("");
  const [spClientSecret, setSpClientSecret] = useState("");

  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [manualName, setManualName] = useState("");
  const [manualSubId, setManualSubId] = useState("");
  const [manualSubIdError, setManualSubIdError] = useState("");
  const [csvErrors, setCsvErrors] = useState<string[]>([]);

  const [testResult, setTestResult] = useState<{
    ok: boolean;
    subscriptions?: string[];
    error?: string;
  } | null>(null);
  const [saveResult, setSaveResult] = useState<{
    error?: string;
    success?: boolean;
    count?: number;
  } | null>(null);

  const [isTesting, startTest] = useTransition();
  const [isSaving, startSave] = useTransition();
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleCsvUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      const { subs, errors } = parseSubscriptionCsv(text);
      setCsvErrors(errors);
      setSaveResult(null);
      if (subs.length > 0) {
        if (!tenantId && subs[0].tenantId) setTenantId(subs[0].tenantId);
        setSubscriptions((prev) => {
          const existing = new Set(prev.map((s) => s.subscriptionId));
          return [...prev, ...subs.filter((s) => !existing.has(s.subscriptionId))];
        });
      }
    };
    reader.readAsText(file);
    e.target.value = "";
  }

  function addManual() {
    const subId = manualSubId.trim();
    if (!subId) return;
    if (!isGuid(subId)) {
      setManualSubIdError("Must be a GUID (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)");
      return;
    }
    if (subscriptions.some((s) => s.subscriptionId === subId)) {
      setManualSubIdError("This subscription ID is already in the list.");
      return;
    }
    setManualSubIdError("");
    setSubscriptions((prev) => [
      ...prev,
      { name: manualName.trim() || subId, subscriptionId: subId },
    ]);
    setManualName("");
    setManualSubId("");
    setSaveResult(null);
  }

  function removeSubscription(subscriptionId: string) {
    setSubscriptions((prev) => prev.filter((s) => s.subscriptionId !== subscriptionId));
    setSaveResult(null);
  }

  function handleTest() {
    setTestResult(null);
    startTest(async () => {
      const result = await testAzureConnection({ tenantId, spClientId, spClientSecret });
      setTestResult(result);
    });
  }

  function handleSave() {
    setSaveResult(null);
    startSave(async () => {
      const result = await addBulkCredentials({
        engagementId,
        tenantId,
        spClientId,
        spClientSecret,
        subscriptions,
      });
      setSaveResult(result);
      if (result.success) {
        setSubscriptions([]);
        setManualName("");
        setManualSubId("");
        setCsvErrors([]);
        setTestResult(null);
      }
    });
  }

  const canTest = !!tenantId && !!spClientId && !!spClientSecret;
  const canSave = canTest && subscriptions.length > 0 && !isSaving;

  return (
    <div className="space-y-5">
      {/* Platform tabs */}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setPlatform("AZURE")}
          className={`rounded-lg px-4 py-1.5 text-sm font-medium transition-colors ${
            platform === "AZURE"
              ? "bg-teal-700 text-white"
              : "bg-navy-100/60 dark:bg-navy-700/60 text-navy-400 dark:text-navy-300 hover:bg-navy-200 dark:hover:bg-navy-700"
          }`}
        >
          Azure
        </button>
        <button
          type="button"
          disabled
          title="AWS support coming soon"
          className="flex items-center gap-1.5 rounded-lg bg-navy-50 dark:bg-navy-700/30 px-4 py-1.5 text-sm font-medium text-navy-500 cursor-not-allowed"
        >
          AWS
          <span className="rounded-full bg-navy-100/60 dark:bg-navy-700/60 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-navy-400">
            soon
          </span>
        </button>
      </div>

      {platform === "AZURE" && (
        <div className="space-y-6">
          {/* ── Authentication ── */}
          <div>
            <div className="mb-3 flex items-center justify-between">
              <p className="label-caps text-navy-400">Authentication</p>
              <SpHelpModal />
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <label className="block text-sm font-medium text-navy-400 dark:text-navy-300">Tenant ID</label>
                <input
                  type="text"
                  value={tenantId}
                  onChange={(e) => setTenantId(e.target.value)}
                  placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                  autoComplete="off"
                  className={INPUT_CLS}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-navy-400 dark:text-navy-300">SP Client ID</label>
                <input
                  type="text"
                  value={spClientId}
                  onChange={(e) => setSpClientId(e.target.value)}
                  placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                  autoComplete="off"
                  className={INPUT_CLS}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-navy-400 dark:text-navy-300">SP Client Secret</label>
                <input
                  type="password"
                  value={spClientSecret}
                  onChange={(e) => setSpClientSecret(e.target.value)}
                  placeholder="••••••••••••••••"
                  autoComplete="new-password"
                  className={INPUT_CLS}
                />
              </div>
            </div>
          </div>

          {/* ── Subscriptions ── */}
          <div>
            <div className="mb-3 flex items-center justify-between">
              <p className="label-caps text-navy-400">
                Subscriptions
                {subscriptions.length > 0 && (
                  <span className="ml-1.5 font-normal normal-case text-navy-500">
                    ({subscriptions.length} pending)
                  </span>
                )}
              </p>
              <div className="flex items-center gap-4 text-xs">
                <button type="button" onClick={downloadTemplate} className="text-teal-700 dark:text-teal-400 hover:underline">
                  Download template
                </button>
                <label className="cursor-pointer text-teal-700 dark:text-teal-400 hover:underline">
                  Import CSV
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv,text/csv"
                    onChange={handleCsvUpload}
                    className="sr-only"
                  />
                </label>
              </div>
            </div>

            {csvErrors.length > 0 && (
              <div className="mb-3 rounded-lg border border-amber-800/40 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-xs text-amber-600 dark:text-amber-400">
                {csvErrors.map((err, i) => <p key={i}>{err}</p>)}
              </div>
            )}

            {subscriptions.length > 0 && (
              <div className="mb-3 flex flex-wrap gap-2">
                {subscriptions.map((sub) => (
                  <span
                    key={sub.subscriptionId}
                    className="inline-flex items-center gap-1.5 rounded-full border border-teal-800/40 bg-teal-50 dark:bg-teal-900/20 px-3 py-1 text-xs text-teal-700 dark:text-teal-300"
                  >
                    <span className="font-medium">{sub.name}</span>
                    <span className="text-teal-700 dark:text-teal-500">{sub.subscriptionId.slice(0, 8)}…</span>
                    <button
                      type="button"
                      onClick={() => removeSubscription(sub.subscriptionId)}
                      className="ml-0.5 rounded-full p-0.5 text-teal-700 dark:text-teal-400 hover:bg-teal-50 dark:hover:bg-teal-800/40"
                      title={`Remove ${sub.name}`}
                    >
                      ✕
                    </button>
                  </span>
                ))}
              </div>
            )}

            <div className="flex gap-2">
              <input
                type="text"
                value={manualName}
                onChange={(e) => setManualName(e.target.value)}
                placeholder="Subscription name"
                autoComplete="off"
                className="w-48 shrink-0 rounded-lg border border-navy-600/50 bg-white/60 dark:bg-navy-800/60 px-3 py-2 text-sm text-navy-800 dark:text-navy-100 placeholder-navy-500 focus:border-teal-500 focus:outline-none focus:ring-1 focus:ring-teal-500"
              />
              <div className="flex flex-1 flex-col">
                <input
                  type="text"
                  value={manualSubId}
                  onChange={(e) => { setManualSubId(e.target.value); setManualSubIdError(""); }}
                  onKeyDown={(e) => e.key === "Enter" && addManual()}
                  placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                  autoComplete="off"
                  className={`block w-full rounded-lg border px-3 py-2 text-sm text-navy-800 dark:text-navy-100 placeholder-navy-500 focus:outline-none focus:ring-1 bg-white/60 dark:bg-navy-800/60 ${
                    manualSubIdError
                      ? "border-red-700/60 focus:border-red-500 focus:ring-red-500"
                      : "border-navy-600/50 focus:border-teal-500 focus:ring-teal-500"
                  }`}
                />
                {manualSubIdError && (
                  <p className="mt-1 text-xs text-red-600 dark:text-red-400">{manualSubIdError}</p>
                )}
              </div>
              <button
                type="button"
                onClick={addManual}
                disabled={!manualSubId.trim()}
                className="shrink-0 rounded-lg border border-navy-600/50 bg-navy-100/60 dark:bg-navy-700/40 px-3 py-2 text-sm font-medium text-navy-500 dark:text-navy-200 hover:bg-navy-100/60 dark:hover:bg-navy-700/60 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Add
              </button>
            </div>
            <p className="mt-1.5 text-xs text-navy-500">
              Add subscriptions individually or import a CSV. Tenant ID from CSV auto-fills above if blank.
            </p>
          </div>

          {testResult && (
            <div className={`rounded-lg px-3 py-2 text-sm ${testResult.ok ? "border border-teal-800/40 bg-teal-50 dark:bg-teal-900/20 text-teal-700 dark:text-teal-300" : "border border-red-800/40 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400"}`}>
              {testResult.ok ? (
                <>
                  <p className="font-medium">Connection successful</p>
                  {testResult.subscriptions && testResult.subscriptions.length > 0 && (
                    <ul className="mt-1 list-disc pl-4 text-xs">
                      {testResult.subscriptions.slice(0, 10).map((s) => <li key={s}>{s}</li>)}
                      {testResult.subscriptions.length > 10 && (
                        <li>+{testResult.subscriptions.length - 10} more</li>
                      )}
                    </ul>
                  )}
                </>
              ) : (
                <p>{testResult.error}</p>
              )}
            </div>
          )}

          {saveResult && (
            <div className={`rounded-lg px-3 py-2 text-sm ${saveResult.success ? "border border-teal-800/40 bg-teal-50 dark:bg-teal-900/20 text-teal-700 dark:text-teal-300" : "border border-red-800/40 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400"}`}>
              {saveResult.success
                ? `${saveResult.count} subscription${saveResult.count !== 1 ? "s" : ""} saved.`
                : saveResult.error}
            </div>
          )}

          <div className="flex items-center justify-end gap-3 pt-1">
            <button
              type="button"
              onClick={handleTest}
              disabled={isTesting || !canTest}
              className="inline-flex items-center rounded-lg border border-navy-600/50 bg-navy-100/60 dark:bg-navy-700/40 px-4 py-2 text-sm font-medium text-navy-500 dark:text-navy-200 hover:bg-navy-100/60 dark:hover:bg-navy-700/60 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isTesting ? "Testing…" : "Test connection"}
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={!canSave}
              className="inline-flex items-center rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSaving
                ? "Saving…"
                : subscriptions.length > 1
                  ? `Save ${subscriptions.length} subscriptions`
                  : "Save connection"}
            </button>
          </div>
        </div>
      )}

      {platform === "AWS" && (
        <div className="rounded-xl border border-dashed border-navy-600/40 p-8 text-center">
          <p className="text-sm text-navy-400">AWS connections aren&apos;t available in this release.</p>
          <p className="mt-1 text-xs text-navy-500">Azure is fully supported — switch to Azure to add a connection.</p>
        </div>
      )}
    </div>
  );
}
