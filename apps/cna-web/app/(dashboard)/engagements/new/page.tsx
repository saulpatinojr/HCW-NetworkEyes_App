import { createEngagement } from "@/app/(dashboard)/dashboard/actions";
import { SubmitButton } from "@/components/ui/submit-button";
import Link from "next/link";

const inputClasses =
  "mt-1 block w-full rounded-lg glass-sm px-3 py-2 text-sm text-navy-800 dark:text-navy-100 placeholder:text-navy-300 dark:placeholder:text-navy-400 focus:outline-none focus:ring-2 focus:ring-teal-400/50";

export default function NewEngagementPage() {
  return (
    <div className="mx-auto max-w-lg">
      <div className="mb-6">
        <Link
          href="/dashboard"
          className="text-sm text-navy-400 dark:text-navy-300 hover:text-navy-600 dark:hover:text-navy-100"
        >
          ← Back to dashboard
        </Link>
        <h1 className="mt-2 text-2xl font-black tracking-tight text-navy-800 dark:text-navy-50">
          New Engagement
        </h1>
        <p className="mt-1 text-sm text-navy-400 dark:text-navy-300">
          Start a Cloud Network Assessment for a client organization.
        </p>
      </div>

      <form action={createEngagement} className="glass p-6 space-y-5">
        <div>
          <label
            htmlFor="name"
            className="block text-sm font-semibold text-navy-700 dark:text-navy-100"
          >
            Engagement name
          </label>
          <input
            id="name"
            name="name"
            type="text"
            required
            placeholder="e.g. ACME Corp — Q2 2026 Network Assessment"
            className={inputClasses}
          />
        </div>

        <div>
          <label
            htmlFor="clientOrg"
            className="block text-sm font-semibold text-navy-700 dark:text-navy-100"
          >
            Client organization
          </label>
          <input
            id="clientOrg"
            name="clientOrg"
            type="text"
            required
            placeholder="e.g. ACME Corp"
            className={inputClasses}
          />
        </div>

        <div className="flex items-center justify-end gap-3 pt-2">
          <Link
            href="/dashboard"
            className="text-sm text-navy-400 dark:text-navy-300 hover:text-navy-600 dark:hover:text-navy-100"
          >
            Cancel
          </Link>
          <SubmitButton loadingText="Creating…">Create engagement</SubmitButton>
        </div>
      </form>
    </div>
  );
}
