import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import { FindingsClient, type FindingItem } from "./findings-client";

interface PageProps {
  params: Promise<{ id: string }>;
}

// ─── MS Learn URL resolution ───────────────────────────────────────────────────

const MSLEARN_KEYWORDS: Array<[RegExp, string]> = [
  [/azure firewall/i,              "https://learn.microsoft.com/en-us/azure/well-architected/service-guides/azure-firewall"],
  [/ddos/i,                        "https://learn.microsoft.com/en-us/azure/ddos-protection/ddos-protection-overview"],
  [/bastion/i,                     "https://learn.microsoft.com/en-us/azure/bastion/bastion-overview"],
  [/private endpoint|private link/i, "https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-overview"],
  [/nat gateway/i,                 "https://learn.microsoft.com/en-us/azure/nat-gateway/nat-overview"],
  [/expressroute/i,                "https://learn.microsoft.com/en-us/azure/expressroute/expressroute-introduction"],
  [/vpn gateway|site.to.site/i,   "https://learn.microsoft.com/en-us/azure/vpn-gateway/vpn-gateway-about-vpngateways"],
  [/peering/i,                     "https://learn.microsoft.com/en-us/azure/virtual-network/virtual-network-peering-overview"],
  [/application gateway|waf/i,    "https://learn.microsoft.com/en-us/azure/application-gateway/overview"],
  [/load balancer/i,               "https://learn.microsoft.com/en-us/azure/load-balancer/load-balancer-overview"],
  [/public ip/i,                   "https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/public-ip-addresses"],
  [/nsg|network security group/i,  "https://learn.microsoft.com/en-us/azure/virtual-network/network-security-groups-overview"],
  [/route table|user.defined route|udr/i, "https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-udr-overview"],
  [/subnet/i,                      "https://learn.microsoft.com/en-us/azure/virtual-network/virtual-network-manage-subnet"],
  [/vnet|virtual network/i,        "https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-overview"],
  [/flow log|network watcher/i,   "https://learn.microsoft.com/en-us/azure/network-watcher/network-watcher-monitoring-overview"],
  [/encryption|tls|certificate/i, "https://learn.microsoft.com/en-us/azure/security/fundamentals/encryption-overview"],
  [/rbac|role.based|privileged/i, "https://learn.microsoft.com/en-us/azure/role-based-access-control/overview"],
  [/diagnostic|monitor|log analytics/i, "https://learn.microsoft.com/en-us/azure/azure-monitor/overview"],
  [/policy|compliance/i,           "https://learn.microsoft.com/en-us/azure/governance/policy/overview"],
];

const MSLEARN_BY_CATEGORY: Record<string, string> = {
  "Access Control":       "https://learn.microsoft.com/en-us/azure/role-based-access-control/overview",
  "Network Security":     "https://learn.microsoft.com/en-us/azure/security/fundamentals/network-overview",
  "Network Segmentation": "https://learn.microsoft.com/en-us/azure/virtual-network/network-security-groups-overview",
  "Network Protection":   "https://learn.microsoft.com/en-us/azure/ddos-protection/ddos-protection-overview",
  "Application Security": "https://learn.microsoft.com/en-us/azure/application-gateway/overview",
  "Routing & Transit":    "https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-udr-overview",
  "Encryption":           "https://learn.microsoft.com/en-us/azure/security/fundamentals/encryption-overview",
  "Compliance":           "https://learn.microsoft.com/en-us/azure/governance/policy/overview",
  "Configuration":        "https://learn.microsoft.com/en-us/azure/governance/policy/overview",
};

function getMsLearnUrl(title: string, category: string): string {
  for (const [pattern, url] of MSLEARN_KEYWORDS) {
    if (pattern.test(title)) return url;
  }
  return (
    MSLEARN_BY_CATEGORY[category] ??
    "https://learn.microsoft.com/en-us/azure/security/fundamentals/network-overview"
  );
}

export default async function FindingsPage({ params }: PageProps) {
  const { id } = await params;
  const session = await auth();

  const engagement = await prisma.engagement.findUnique({
    where: { id },
    select: { id: true, members: true },
  });
  if (!engagement) notFound();

  const isMember = engagement.members.some((m) => m.userId === session?.user?.id);
  if (!isMember) notFound();

  const rawFindings = await prisma.finding.findMany({
    where: { engagementId: id },
    orderBy: [{ severity: "asc" }, { category: "asc" }],
  });

  // ── Non-destructive display dedupe ────────────────────────────────────────────
  // Legacy duplicate rows (from pre-dedup-fix syncs) are deleted by
  // dedupeDiscoveryFindings() when a discovery run starts — never here: a GET
  // must not delete rows. Until that runs, hide older copies per
  // (credentialId, title) group for display only.
  const seen = new Set<string>();
  const keep = new Set<string>();
  const newestFirst = [...rawFindings].sort(
    (a, b) => b.createdAt.getTime() - a.createdAt.getTime(),
  );
  for (const f of newestFirst) {
    if (f.aiGenerated) {
      keep.add(f.id);
      continue;
    }
    const key = `${f.credentialId ?? "__none__"}::${f.title.toLowerCase().trim()}`;
    if (!seen.has(key)) {
      seen.add(key);
      keep.add(f.id);
    }
  }

  // Attach MS Learn URLs server-side so the client doesn't need the lookup tables
  const findings: FindingItem[] = rawFindings.filter((f) => keep.has(f.id)).map((f) => ({
    id: f.id,
    title: f.title,
    category: f.category,
    severity: f.severity,
    description: f.description,
    recommendation: f.recommendation,
    aiGenerated: f.aiGenerated,
    msLearnUrl: getMsLearnUrl(f.title, f.category),
  }));

  return <FindingsClient findings={findings} />;
}
