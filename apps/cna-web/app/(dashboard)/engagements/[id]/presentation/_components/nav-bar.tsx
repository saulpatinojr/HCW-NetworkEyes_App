"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const SUB_PAGES = [
  { path: "",            label: "Overview"    },
  { path: "/executive",  label: "Executive"   },
  { path: "/technical",  label: "Technical"   },
  { path: "/remediation",label: "Remediation" },
  { path: "/compliance", label: "Compliance"  },
] as const;

export function PresentationNavBar({ base }: { base: string }) {
  const pathname = usePathname();

  return (
    <nav className="mb-5 flex items-center gap-1 overflow-x-auto rounded-xl border border-navy-100/60 bg-navy-50 p-1 dark:border-navy-700/40 dark:bg-navy-800/40">
      {SUB_PAGES.map((p) => {
        const href = `${base}${p.path}`;
        const isActive =
          p.path === ""
            ? pathname === base
            : pathname === href || pathname.startsWith(`${href}/`);

        return (
          <Link
            key={p.path}
            href={href}
            className={[
              "flex-1 whitespace-nowrap rounded-lg px-4 py-1.5 text-center text-sm font-medium transition-colors",
              isActive
                ? "bg-teal-600 text-white shadow-sm"
                : "text-navy-400 hover:bg-navy-100 hover:text-navy-800 dark:text-navy-300 dark:hover:bg-navy-700/60 dark:hover:text-navy-100",
            ].join(" ")}
          >
            {p.label}
          </Link>
        );
      })}
    </nav>
  );
}
