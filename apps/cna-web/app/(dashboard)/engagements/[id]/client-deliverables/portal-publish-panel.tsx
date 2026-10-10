"use client";

import { useState, useTransition } from "react";
import { publishClientPortal } from "./actions";

interface LatestPublication {
  issuedAt: string;
  expiresAt: string;
  deliverableCount: number;
}

export function PortalPublishPanel({
  engagementId,
  hasPublishedDeliverables,
  latestPublication,
}: {
  engagementId: string;
  hasPublishedDeliverables: boolean;
  latestPublication: LatestPublication | null;
}) {
  const [isPublishing, startPublish] = useTransition();
  const [result, setResult] = useState<{
    error?: string;
    portalUrl?: string;
    expiresAt?: string;
    deliverableCount?: number;
  } | null>(null);
  const [copied, setCopied] = useState(false);

  const isLive =
    latestPublication !== null && new Date(latestPublication.expiresAt) > new Date();

  function handlePublish() {
    setResult(null);
    setCopied(false);
    startPublish(async () => {
      const r = await publishClientPortal(engagementId);
      setResult(r);
    });
  }

  async function handleCopy() {
    if (!result?.portalUrl) return;
    try {
      await navigator.clipboard.writeText(result.portalUrl);
      setCopied(true);
    } catch {
      // Selection fallback: the URL is visible in the input below.
    }
  }

  return (
    <section className="glass p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold text-navy-800 dark:text-navy-100">
            Client portal
          </h3>
          <p className="mt-1 max-w-xl text-sm text-navy-400">
            Publishes the published deliverables to a private storage container and issues a
            time-limited link the client can open without signing in. The link expires
            automatically and is shown only once — copy it now.
          </p>
          {latestPublication && !result?.portalUrl && (
            <p className="mt-2 text-xs text-navy-500">
              {isLive ? (
                <>
                  Portal live — {latestPublication.deliverableCount} deliverable(s), expires{" "}
                  {new Date(latestPublication.expiresAt).toLocaleString()}. Re-publish to issue
                  a fresh link.
                </>
              ) : (
                <>
                  Last portal link expired{" "}
                  {new Date(latestPublication.expiresAt).toLocaleString()}. Re-publish to issue
                  a new one.
                </>
              )}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={handlePublish}
          disabled={isPublishing || !hasPublishedDeliverables}
          title={
            hasPublishedDeliverables
              ? undefined
              : "Publish at least one deliverable first"
          }
          className="inline-flex items-center rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isPublishing
            ? "Publishing…"
            : latestPublication
              ? "Re-publish portal"
              : "Publish portal"}
        </button>
      </div>

      {result?.error && (
        <div className="mt-4 rounded-lg border border-red-800/40 bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">
          {result.error}
        </div>
      )}

      {result?.portalUrl && (
        <div className="mt-4 rounded-lg border border-teal-800/40 bg-teal-50 px-3 py-3 text-sm text-teal-700 dark:bg-teal-900/20 dark:text-teal-300">
          <p className="font-medium">
            Portal published — {result.deliverableCount} deliverable(s). Expires{" "}
            {result.expiresAt ? new Date(result.expiresAt).toLocaleString() : "in 7 days"}.
          </p>
          <div className="mt-2 flex items-center gap-2">
            <input
              type="text"
              readOnly
              value={result.portalUrl}
              onFocus={(e) => e.target.select()}
              className="w-full rounded-lg border border-teal-800/30 bg-white/70 px-3 py-1.5 text-xs text-navy-800 dark:bg-navy-800/60 dark:text-navy-100"
            />
            <button
              type="button"
              onClick={handleCopy}
              className="shrink-0 rounded-lg border border-teal-800/40 px-3 py-1.5 text-xs font-medium hover:bg-teal-100/60 dark:hover:bg-teal-900/40"
            >
              {copied ? "Copied" : "Copy link"}
            </button>
          </div>
          <p className="mt-2 text-xs opacity-80">
            This link is not stored anywhere — if it is lost, re-publish to issue a new one.
          </p>
        </div>
      )}
    </section>
  );
}
