const STATUS_COLORS: Record<string, string> = {
  DRAFT:     "bg-navy-50   text-navy-500  border border-navy-100  dark:bg-navy-800/50 dark:text-navy-300 dark:border-navy-700",
  DISCOVERY: "bg-teal-50   text-teal-700  border border-teal-200  dark:bg-teal-900/40 dark:text-teal-300 dark:border-teal-800",
  ANALYSIS:  "bg-amber-50  text-amber-700 border border-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-800",
  REVIEW:    "bg-violet-50 text-violet-700 border border-violet-200 dark:bg-violet-900/30 dark:text-violet-300 dark:border-violet-800",
  DELIVERED: "bg-green-50  text-green-700 border border-green-200 dark:bg-green-900/30 dark:text-green-300 dark:border-green-800",
};

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL:      "bg-red-50    text-red-700    border border-red-200    dark:bg-red-900/30    dark:text-red-300    dark:border-red-800",
  HIGH:          "bg-orange-50 text-orange-700 border border-orange-200 dark:bg-orange-900/30 dark:text-orange-300 dark:border-orange-800",
  MEDIUM:        "bg-amber-50  text-amber-700  border border-amber-200  dark:bg-amber-900/30  dark:text-amber-300  dark:border-amber-800",
  LOW:           "bg-blue-50   text-blue-700   border border-blue-200   dark:bg-blue-900/30   dark:text-blue-300   dark:border-blue-800",
  INFORMATIONAL: "bg-navy-50   text-navy-500   border border-navy-100   dark:bg-navy-800/50   dark:text-navy-300   dark:border-navy-700",
};

const DOCTYPE_COLORS: Record<string, string> = {
  CLIENT_ARCHITECTURE: "bg-indigo-50  text-indigo-700 border border-indigo-200 dark:bg-indigo-900/30 dark:text-indigo-300 dark:border-indigo-800",
  COMPLIANCE_FRAMEWORK: "bg-violet-50 text-violet-700 border border-violet-200 dark:bg-violet-900/30 dark:text-violet-300 dark:border-violet-800",
  NETWORK_DIAGRAM:     "bg-teal-50   text-teal-700   border border-teal-200   dark:bg-teal-900/30   dark:text-teal-300   dark:border-teal-800",
  CONFIGURATION_EXPORT: "bg-navy-50  text-navy-600   border border-navy-100   dark:bg-navy-800/50   dark:text-navy-300   dark:border-navy-700",
  OTHER:               "bg-gray-50   text-gray-500   border border-gray-200   dark:bg-gray-800/50   dark:text-gray-400   dark:border-gray-700",
};

const JOB_COLORS: Record<string, string> = {
  QUEUED:    "bg-navy-50   text-navy-500  border border-navy-100  dark:bg-navy-800/50 dark:text-navy-300 dark:border-navy-700",
  RUNNING:   "bg-teal-50   text-teal-700  border border-teal-200  dark:bg-teal-900/40 dark:text-teal-300 dark:border-teal-800",
  COMPLETED: "bg-green-50  text-green-700 border border-green-200 dark:bg-green-900/30 dark:text-green-300 dark:border-green-800",
  FAILED:    "bg-red-50    text-red-700   border border-red-200   dark:bg-red-900/30   dark:text-red-300   dark:border-red-800",
  CANCELLED: "bg-gray-50   text-gray-500  border border-gray-200  dark:bg-gray-800/50  dark:text-gray-400  dark:border-gray-700",
};

const LABELS: Record<string, string> = {
  DRAFT: "Draft", DISCOVERY: "Discovery", ANALYSIS: "Analysis",
  REVIEW: "Review", DELIVERED: "Delivered",
  CRITICAL: "Critical", HIGH: "High", MEDIUM: "Medium",
  LOW: "Low", INFORMATIONAL: "Info",
  CLIENT_ARCHITECTURE: "Architecture", COMPLIANCE_FRAMEWORK: "Compliance",
  NETWORK_DIAGRAM: "Diagram", CONFIGURATION_EXPORT: "Config", OTHER: "Other",
  QUEUED: "Queued", RUNNING: "Running", COMPLETED: "Completed",
  FAILED: "Failed", CANCELLED: "Cancelled",
};

interface StatusBadgeProps {
  value: string;
  variant: "status" | "severity" | "doctype" | "job";
}

export function StatusBadge({ value, variant }: StatusBadgeProps) {
  const colorMap =
    variant === "status"
      ? STATUS_COLORS
      : variant === "severity"
        ? SEVERITY_COLORS
        : variant === "job"
          ? JOB_COLORS
          : DOCTYPE_COLORS;

  const color = colorMap[value] ?? "bg-gray-50 text-gray-500 border border-gray-200";
  const label = LABELS[value] ?? value;

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold leading-none ${color}`}
    >
      {label}
    </span>
  );
}
