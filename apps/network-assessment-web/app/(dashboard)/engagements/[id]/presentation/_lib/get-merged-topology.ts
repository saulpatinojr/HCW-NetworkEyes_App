import { prisma } from "@/lib/prisma";
import type { Topology } from "./metrics";

/**
 * Fetches all completed discovery jobs for the engagement and merges their
 * topologies into a single object — one entry per credential's latest job,
 * deduplicating subscriptions by subscription_id. This is the same pattern
 * used by the deliverables generator and the inventory page.
 */
export async function getMergedTopology(
  engagementId: string,
): Promise<{ topology: Topology | null; jobDate: Date | null }> {
  try {
    const jobs = await prisma.discoveryJob.findMany({
      where: { engagementId, status: "COMPLETED" },
      orderBy: { completedAt: "desc" },
      select: { topologyJson: true, completedAt: true, credentialId: true },
      take: 100,
    });

    if (!jobs.length) return { topology: null, jobDate: null };

    // Latest job per credential (jobs are already ordered completedAt desc)
    const latestByCredential = new Map<string, { topologyJson: string; completedAt: Date | null }>();
    for (const job of jobs) {
      const key = job.credentialId ?? "__none__";
      if (!latestByCredential.has(key) && job.topologyJson) {
        latestByCredential.set(key, { topologyJson: job.topologyJson, completedAt: job.completedAt });
      }
    }

    if (latestByCredential.size === 0) return { topology: null, jobDate: null };

    // Most recent completedAt across all selected jobs
    const jobDate =
      [...latestByCredential.values()]
        .map((j) => j.completedAt)
        .filter((d): d is Date => d !== null)
        .sort((a, b) => b.getTime() - a.getTime())[0] ?? null;

    if (latestByCredential.size === 1) {
      const { topologyJson } = [...latestByCredential.values()][0];
      try {
        return { topology: JSON.parse(topologyJson) as Topology, jobDate };
      } catch {
        return { topology: null, jobDate };
      }
    }

    // Merge: deduplicate subscriptions by subscription_id across all credentials
    const seenSubIds = new Set<string>();
    const mergedSubs: Topology["subscriptions"] = [];

    for (const { topologyJson } of latestByCredential.values()) {
      try {
        const topo = JSON.parse(topologyJson) as Topology;
        for (const sub of topo.subscriptions ?? []) {
          if (sub.subscription_id && !seenSubIds.has(sub.subscription_id)) {
            seenSubIds.add(sub.subscription_id);
            mergedSubs.push(sub);
          }
        }
      } catch { /* skip malformed JSON */ }
    }

    return { topology: { subscriptions: mergedSubs }, jobDate };
  } catch {
    return { topology: null, jobDate: null };
  }
}
