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
        className="text-xs text-teal-700 dark:text-teal-400 hover:underline"
      >
        How do I create these?
      </button>

      <dialog
        ref={dialogRef}
        onClose={() => setOpen(false)}
        onClick={handleBackdropClick}
        aria-labelledby="sp-modal-title"
        className="m-auto w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-xl bg-white dark:bg-navy-900 shadow-2xl border-0 p-0 outline-none backdrop:bg-black/40"
      >
        <div className="relative z-10 w-full bg-white dark:bg-navy-900">
            {/* Header */}
            <div className="sticky top-0 flex items-center justify-between border-b border-gray-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-6 py-4">
              <div>
                <h2 id="sp-modal-title" className="text-base font-semibold text-gray-900 dark:text-navy-50">
                  Granting the appliance read access
                </h2>
                <p className="mt-0.5 text-xs text-gray-500 dark:text-navy-400">
                  The appliance signs in with its own managed identity. There is
                  no app registration to create and no secret to copy.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close dialog"
                className="rounded-lg p-1.5 text-gray-400 dark:text-navy-500 hover:bg-gray-100 dark:hover:bg-navy-800 hover:text-gray-600 dark:hover:text-navy-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500"
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
            <div className="space-y-6 px-6 py-5 text-sm text-gray-700 dark:text-navy-200">

              {/* Why a managed identity */}
              <div className="rounded-lg bg-teal-50 dark:bg-teal-900/20 px-4 py-3 text-xs text-teal-900 dark:text-teal-200">
                <p className="font-semibold">How does the appliance authenticate?</p>
                <p className="mt-1">
                  The appliance runs with a user-assigned managed identity that the
                  platform issues tokens to. Nothing is typed into this form except
                  the tenant and the subscriptions to scan; no password, certificate
                  or client secret is ever stored. Access is granted by assigning
                  roles to that identity (<strong>Reader</strong> on each
                  subscription, plus the optional reader roles in the table below).
                </p>
              </div>

              {/* Step 1 */}
              <Step number={1} title="Find the appliance identity">
                <ol className="list-decimal space-y-1.5 pl-5 text-gray-600 dark:text-navy-300">
                  <li>
                    Open the{" "}
                    <ExternalLink href="https://portal.azure.com/#view/HubsExtension/BrowseResource/resourceType/Microsoft.ManagedIdentity%2FuserAssignedIdentities">
                      Azure Portal → Managed Identities
                    </ExternalLink>
                  </li>
                  <li>
                    Open the managed identity this app runs as (your deployment
                    created it; its name is part of your deployment record)
                  </li>
                  <li>
                    On the Overview page note the <strong>Name</strong>; it is the
                    member you will add in step 3
                  </li>
                </ol>
              </Step>

              {/* Step 2 */}
              <Step number={2} title="Copy your Tenant ID">
                <p className="mb-2 text-gray-600 dark:text-navy-300">
                  On the identity&apos;s Overview page:
                </p>
                <div className="space-y-2 rounded-lg border border-gray-200 dark:border-navy-700 bg-gray-50 dark:bg-navy-800/60 p-3">
                  <FieldRow
                    label="Tenant ID"
                    target="Tenant ID field"
                    note="Identifies the Entra tenant the identity lives in"
                  />
                </div>
              </Step>

              {/* Step 3 */}
              <Step number={3} title="Assign Reader (and the optional reader roles) on your subscriptions">
                <p className="mb-2 text-gray-600 dark:text-navy-300">
                  Repeat for each subscription you want CNA to discover:
                </p>
                <ol className="list-decimal space-y-1.5 pl-5 text-gray-600 dark:text-navy-300">
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
                    <Code>Reader</Code> (then, if you want those checks, the optional roles
                    in the table below)
                  </li>
                  <li>
                    <strong>Members:</strong> choose <strong>Managed identity</strong>,
                    then the appliance identity from step 1
                  </li>
                  <li>
                    Click <Kbd>Review + assign</Kbd> twice to confirm
                  </li>
                </ol>
                <p className="mt-2 text-xs text-gray-500 dark:text-navy-400">
                  Tip: if you have hundreds of subscriptions, assign Reader at the
                  Management Group level and it propagates to all child subscriptions
                  automatically.
                </p>
              </Step>

              {/* Step 4 */}
              <Step number={4} title="Test access">
                <p className="text-gray-600 dark:text-navy-300">
                  Save the tenant, then press <Kbd>Test access</Kbd>. The appliance lists
                  the subscriptions its identity can read; any you entered that are
                  missing from the list still need a role assignment.
                </p>
              </Step>

              {/* Roles table */}
              <div className="rounded-lg border border-amber-100 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-900/20 px-4 py-3 text-xs">
                <p className="mb-1.5 font-semibold text-amber-800 dark:text-amber-300">
                  Why Reader, and not a write role?
                </p>
                <p className="text-amber-700 dark:text-amber-300 mb-2">
                  The scan is read-only: every call it makes is a read, including listing
                  virtual network gateways. The only non-read calls are the BGP state actions
                  (peer status, learned and advertised routes), which the custom role
                  <Code>CNA Network BGP Reader</Code> grants and nothing else. A write role
                  gives CNA permissions it never uses.
                </p>
                <p className="font-semibold text-gray-700 dark:text-navy-200 mb-1">Roles, and what each unlocks:</p>
                <table className="w-full text-left text-gray-600 dark:text-navy-300">
                  <thead>
                    <tr className="text-gray-500 dark:text-navy-400">
                      <th className="pr-3 font-medium">Role</th>
                      <th className="pr-3 font-medium">Kind</th>
                      <th className="font-medium">Required for</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ROLES.map((r) => (
                      <tr key={r.role} className="align-top">
                        <td className="pr-3 py-0.5"><Code>{r.role}</Code></td>
                        <td className="pr-3 py-0.5">{r.kind}</td>
                        <td className="py-0.5">{r.purpose}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-2 text-gray-500 dark:text-navy-400">
                  The custom role&apos;s six actions are listed in{" "}
                  <Code>docs/roles/cna-network-bgp-reader.json</Code> and are marked for
                  verification against the current Microsoft.Network operations before the
                  role is created.
                </p>
              </div>

              {/* Microsoft docs link */}
              <p className="text-xs text-gray-500 dark:text-navy-400">
                Microsoft documentation:{" "}
                <ExternalLink href="https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/how-manage-user-assigned-managed-identities">
                  Manage user-assigned managed identities
                </ExternalLink>
              </p>
            </div>

            {/* Footer */}
            <div className="sticky bottom-0 flex justify-end border-t border-gray-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-6 py-3">
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

// ── Roles (REFACTOR_APP.md section 13, the single source for this table) ─────
// [REVIEW REQUIRED] role decisions; the custom role's actions are [VERIFY actions].

const ROLES = [
  { role: "Reader", kind: "built-in", purpose: "Every export rule and Resource Graph discovery" },
  { role: "Security Reader", kind: "built-in", purpose: "Defender assessments" },
  { role: "Cost Management Reader", kind: "built-in", purpose: "Cost rules (AZ-COST-002/003/005)" },
  { role: "Log Analytics Reader", kind: "built-in", purpose: "Traffic Analytics (AZ-NET-014 live form)" },
  { role: "CNA Network BGP Reader", kind: "custom", purpose: "BGP peer status, learned and advertised routes" },
  { role: "Management Group Reader", kind: "built-in", purpose: "Management-group tree (optional)" },
] as const;

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
        <h3 className="font-semibold text-gray-900 dark:text-navy-50">{title}</h3>
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
      <span className="font-medium text-gray-700 dark:text-navy-200">{label}</span>
      <span className="text-right text-gray-500 dark:text-navy-400">
        → paste into <span className="font-medium text-gray-800 dark:text-navy-100">{target}</span>
        <br />
        <span className="text-gray-500 dark:text-navy-400">{note}</span>
      </span>
    </div>
  );
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded bg-gray-100 dark:bg-navy-800 px-1 py-0.5 font-mono text-[11px] text-gray-700 dark:text-navy-200">
      {children}
    </code>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded border border-gray-300 dark:border-navy-600 bg-gray-100 dark:bg-navy-800 px-1.5 py-0.5 font-sans text-[11px] text-gray-700 dark:text-navy-200">
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
      className="inline-flex items-center gap-1 text-teal-700 dark:text-teal-400 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500"
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
