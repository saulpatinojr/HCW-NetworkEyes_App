import { prisma } from "@/lib/prisma";

// Cleanup for a historical bug: before the dedup fix, each discovery sync
// added NEW rows for already-existing findings instead of replacing them.
// Keeps the newest copy per (credentialId, title) group and deletes all older
// duplicates. Idempotent and fast on already-clean data.
//
// Runs only from mutation contexts (starting a discovery run) — never from
// page render: a GET must not delete rows.
export async function dedupeDiscoveryFindings(engagementId: string): Promise<void> {
  try {
    const allDiscovery = await prisma.finding.findMany({
      where: { engagementId, aiGenerated: false },
      orderBy: { createdAt: "desc" },
      select: { id: true, title: true, credentialId: true },
    });
    const seen = new Set<string>();
    const toDelete: string[] = [];
    for (const f of allDiscovery) {
      const key = `${f.credentialId ?? "__none__"}::${f.title.toLowerCase().trim()}`;
      if (seen.has(key)) {
        toDelete.push(f.id);
      } else {
        seen.add(key);
      }
    }
    if (toDelete.length > 0) {
      await prisma.finding.deleteMany({ where: { id: { in: toDelete } } });
    }
  } catch {
    /* non-fatal cleanup */
  }
}
