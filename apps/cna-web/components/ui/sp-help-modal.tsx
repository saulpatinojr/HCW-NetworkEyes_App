"use client";

import { useState, useRef, useEffect } from "react";

export function SpHelpModal() {
  const [open, setOpen] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open) {
      if (!dialog.open) {
        dialog.showModal();
      }
    } else {
      if (dialog.open) {
        dialog.close();
      }
    }
  }, [open]);

  const handleBackdropClick = (e: React.MouseEvent<HTMLDialogElement>) => {
    const dialog = dialogRef.current;
    if (e.target === dialog) {
      setOpen(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="text-xs text-teal-700 hover:underline"
      >
        How do I create these?
      </button>

      <dialog
        ref={dialogRef}
        onClose={() => setOpen(false)}
        onClick={handleBackdropClick}
        aria-labelledby="sp-modal-title"
        className="m-auto w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-xl bg-white shadow-2xl border-0 p-0 outline-none backdrop:bg-black/40"
      >
        <div className="relative z-10 w-full bg-white">
            {/* Header */}
            <div className="sticky top-0 flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
              <div>
                <h2 id="sp-modal-title" className="text-base font-semibold text-gray-900">
                  Creating an Azure Service Principal
                </h2>
                <p className="mt-0.5 text-xs text-gray-500">
                  A Service Principal lets CNA read your Azure tenant without
                  using a personal account.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close dialog"
                className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500"
              >
                <svg
                  className="h-5 w-5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </div>

            {/* Body */}
            <div className="space-y-6 px-6 py-5 text-sm text-gray-700">

              {/* What is an SP */}
              <div className="rounded-lg bg-teal-50 px-4 py-3 text-xs text-teal-900">
                <p className="font-semibold">Why is this needed?</p>
                <p className="mt-1">
                  CNA needs access to your Azure environment to discover network
                  topology, NSG rules, VNets, and firewall configurations. A
                  Service Principal acts like a dedicated "robot user" — it only
                  gets the permissions you explicitly grant (minimum:{" "}
                  <strong>Network Contributor</strong> on each subscription).
                  No personal account credentials are ever stored.
                </p>
              </div>

              {/* Step 1 */}
              <Step number={1} title="Register the application in Entra ID">
                <ol className="list-decimal space-y-1.5 pl-5 text-gray-600">
                  <li>
                    Open the{" "}
                    <ExternalLink href="https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade">
                      Azure Portal → App registrations
                    </ExternalLink>
                  </li>
                  <li>
                    Click <Kbd>+ New registration</Kbd>
                  </li>
                  <li>
                    <strong>Name:</strong> something descriptive, e.g.{" "}
                    <Code>cna-discovery-sp</Code>
                  </li>
                  <li>
                    <strong>Supported account types:</strong> leave as
                    "Accounts in this organizational directory only"
                  </li>
                  <li>
                    Click <Kbd>Register</Kbd>
                  </li>
                </ol>
              </Step>

              {/* Step 2 */}
              <Step number={2} title="Copy your Tenant ID and SP Client ID">
                <p className="mb-2 text-gray-600">
                  On the app's Overview page you'll see two important values:
                </p>
                <div className="space-y-2 rounded-lg border border-gray-200 bg-gray-50 p-3">
                  <FieldRow
                    label="Application (client) ID"
                    target="SP Client ID field"
                    note="Identifies this specific app registration"
                  />
                  <FieldRow
                    label="Directory (tenant) ID"
                    target="Tenant ID field"
                    note="Identifies your Azure Active Directory tenant"
                  />
                </div>
              </Step>

              {/* Step 3 */}
              <Step number={3} title="Create a client secret">
                <ol className="list-decimal space-y-1.5 pl-5 text-gray-600">
                  <li>
                    In the left menu select{" "}
                    <strong>Certificates &amp; secrets</strong>
                  </li>
                  <li>
                    Click <Kbd>+ New client secret</Kbd>
                  </li>
                  <li>
                    Enter a description (e.g. <Code>cna-discovery</Code>) and
                    choose an expiry (24 months is typical)
                  </li>
                  <li>
                    Click <Kbd>Add</Kbd>
                  </li>
                  <li>
                    Copy the <strong>Value</strong> column immediately —{" "}
                    <span className="font-medium text-red-600">
                      it is only shown once.
                    </span>{" "}
                    Paste it into the <strong>SP Client Secret</strong> field.
                  </li>
                </ol>
                <p className="mt-2 rounded bg-amber-50 px-3 py-2 text-xs text-amber-700">
                  If you navigate away before copying, you must delete the
                  secret and create a new one. The ID column is not the secret —
                  only the Value column is.
                </p>
              </Step>

              {/* Step 4 */}
              <Step number={4} title="Grant Network Contributor access to your subscriptions">
                <p className="mb-2 text-gray-600">
                  Repeat for each subscription you want CNA to discover:
                </p>
                <ol className="list-decimal space-y-1.5 pl-5 text-gray-600">
                  <li>
                    Go to{" "}
                    <ExternalLink href="https://portal.azure.com/#view/Microsoft_Azure_Billing/SubscriptionsBlade">
                      Subscriptions
                    </ExternalLink>{" "}
                    and open the target subscription
                  </li>
                  <li>
                    Select <strong>Access control (IAM)</strong> in the left
                    menu
                  </li>
                  <li>
                    Click <Kbd>+ Add</Kbd> → <Kbd>Add role assignment</Kbd>
                  </li>
                  <li>
                    <strong>Role:</strong> search for and select{" "}
                    <Code>Network Contributor</Code>
                  </li>
                  <li>
                    <strong>Members:</strong> click "+ Select members" and
                    search for your app registration name (e.g.{" "}
                    <Code>cna-discovery-sp</Code>)
                  </li>
                  <li>
                    Click <Kbd>Review + assign</Kbd> twice to confirm
                  </li>
                </ol>
                <p className="mt-2 text-xs text-gray-500">
                  Tip: if you have hundreds of subscriptions, assign Network Contributor at
                  the Management Group level and it propagates to all child
                  subscriptions automatically.
                </p>
              </Step>

              {/* Minimum permissions callout */}
              <div className="rounded-lg border border-amber-100 bg-amber-50 px-4 py-3 text-xs">
                <p className="mb-1.5 font-semibold text-amber-800">
                  Why Network Contributor and not Reader?
                </p>
                <p className="text-amber-700 mb-2">
                  Some Azure network APIs (e.g. Virtual Network Gateways) require
                  Network Contributor to enumerate resources across resource groups.
                  CNA only reads — it never creates, modifies, or deletes anything.
                </p>
                <p className="font-semibold text-gray-700 mb-1">Key permissions granted by Network Contributor:</p>
                <ul className="space-y-0.5 text-gray-500">
                  {[
                    "Microsoft.Network/virtualNetworks/read",
                    "Microsoft.Network/networkSecurityGroups/read",
                    "Microsoft.Network/azureFirewalls/read",
                    "Microsoft.Network/virtualNetworkGateways/read",
                    "Microsoft.Network/virtualNetworkGateways/list",
                    "Microsoft.Network/loadBalancers/read",
                    "Microsoft.Network/privateDnsZones/read",
                    "Microsoft.Resources/subscriptions/resourceGroups/read",
                  ].map((p) => (
                    <li key={p}>
                      <Code>{p}</Code>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Microsoft docs link */}
              <p className="text-xs text-gray-500">
                Microsoft documentation:{" "}
                <ExternalLink href="https://learn.microsoft.com/en-us/entra/identity-platform/howto-create-service-principal-portal">
                  Create a service principal in the Azure portal
                </ExternalLink>
              </p>
            </div>

            {/* Footer */}
            <div className="sticky bottom-0 flex justify-end border-t border-gray-200 bg-white px-6 py-3">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-lg bg-teal-500 px-4 py-2 text-sm font-bold text-navy-800 hover:bg-[#00c9a2] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500"
              >
                Got it
              </button>
            </div>
          </div>
        </dialog>
      </>
    );
  }

// ── Small helpers ─────────────────────────────────────────────────────────────

function Step({
  number,
  title,
  children,
}: {
  number: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-teal-500 text-xs font-bold text-navy-800">
          {number}
        </span>
        <h3 className="font-semibold text-gray-900">{title}</h3>
      </div>
      <div className="ml-8">{children}</div>
    </div>
  );
}

function FieldRow({
  label,
  target,
  note,
}: {
  label: string;
  target: string;
  note: string;
}) {
  return (
    <div className="flex items-start justify-between gap-4 text-xs">
      <span className="font-medium text-gray-700">{label}</span>
      <span className="text-right text-gray-500">
        → paste into <span className="font-medium text-gray-800">{target}</span>
        <br />
        <span className="text-gray-400">{note}</span>
      </span>
    </div>
  );
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded bg-gray-100 px-1 py-0.5 font-mono text-[11px] text-gray-700">
      {children}
    </code>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded border border-gray-300 bg-gray-100 px-1.5 py-0.5 font-sans text-[11px] text-gray-700">
      {children}
    </kbd>
  );
}

function ExternalLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-teal-700 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500"
    >
      {children}
      <span className="sr-only">(opens in new tab)</span>
      <svg
        aria-hidden="true"
        focusable="false"
        className="h-3 w-3"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={2}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
        />
      </svg>
    </a>
  );
}
