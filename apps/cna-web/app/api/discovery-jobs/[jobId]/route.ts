import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { NextResponse } from "next/server";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { jobId } = await params;

  const job = await prisma.discoveryJob.findUnique({
    where: { id: jobId },
    include: { engagement: { include: { members: true } } },
  });

  if (!job) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const isMember = job.engagement.members.some((m) => m.userId === session.user!.id);
  if (!isMember) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  // Topology summary — parsed from stored AzureTopology JSON (COMPLETED jobs only)
  type TopologySummary = {
    vnets: number; subnets: number; firewalls: number;
    appGateways: number; dnsZones: number; expressRoutes: number;
    // v1.3 extended fields
    workload: { vmCount: number; acaCount: number; aksCount: number; fnCount: number };
    bgp: { gatewaysWithBgp: number; peersConnected: number; peersDisconnected: number; routesLearned: number };
    observability: { networkWatchers: number; logWorkspaces: number; nsgFlowLogsEnabled: number; nsgTotal: number };
    metricsCollected: boolean;
  };
  let topologySummary: TopologySummary | null = null;

  if (job.status === "COMPLETED" && job.topologyJson) {
    try {
      const topo = JSON.parse(job.topologyJson) as Record<string, unknown>;
      const subs = Array.isArray(topo.subscriptions)
        ? (topo.subscriptions as Record<string, unknown>[])
        : [];

      let vnets = 0, subnets = 0, firewalls = 0, appGateways = 0, dnsZones = 0, expressRoutes = 0;
      let vmCount = 0, acaCount = 0, aksCount = 0, fnCount = 0;
      let gatewaysWithBgp = 0, peersConnected = 0, peersDisconnected = 0, routesLearned = 0;
      let networkWatchers = 0, logWorkspaces = 0, nsgFlowLogsEnabled = 0, nsgTotal = 0;
      let metricsCollected = false;

      for (const sub of subs) {
        // Network topology
        const subVnets = Array.isArray(sub.vnets) ? (sub.vnets as Record<string, unknown>[]) : [];
        vnets += subVnets.length;
        for (const vnet of subVnets) {
          subnets += Array.isArray(vnet.subnets) ? (vnet.subnets as unknown[]).length : 0;
        }
        firewalls += Array.isArray(sub.firewalls) ? (sub.firewalls as unknown[]).length : 0;
        appGateways += Array.isArray(sub.application_gateways) ? (sub.application_gateways as unknown[]).length : 0;
        dnsZones += Array.isArray(sub.private_dns_zones) ? (sub.private_dns_zones as unknown[]).length : 0;
        expressRoutes += Array.isArray(sub.express_route_circuits) ? (sub.express_route_circuits as unknown[]).length : 0;

        // Workload inventory
        const inv = sub.workload_inventory as Record<string, number> | null | undefined;
        if (inv) {
          vmCount += inv.vm_count ?? 0;
          acaCount += inv.aca_count ?? 0;
          aksCount += inv.aks_cluster_count ?? 0;
          fnCount += inv.function_app_count ?? 0;
        }

        // BGP data
        const bgpData = Array.isArray(sub.bgp_data) ? (sub.bgp_data as Record<string, unknown>[]) : [];
        for (const gw of bgpData) {
          if (gw.bgp_enabled) gatewaysWithBgp++;
          routesLearned += (gw.learned_routes_count as number) ?? 0;
          const peers = Array.isArray(gw.peers) ? (gw.peers as Record<string, unknown>[]) : [];
          for (const peer of peers) {
            if (peer.state === "Connected") peersConnected++;
            else if (peer.state !== "Unknown") peersDisconnected++;
          }
        }

        // Observability
        const obs = sub.observability as Record<string, unknown> | null | undefined;
        if (obs) {
          networkWatchers += Array.isArray(obs.network_watchers) ? (obs.network_watchers as unknown[]).length : 0;
          logWorkspaces += Array.isArray(obs.log_analytics_workspaces) ? (obs.log_analytics_workspaces as unknown[]).length : 0;
          nsgFlowLogsEnabled += (obs.nsg_flow_logs_enabled as number) ?? 0;
          nsgTotal += (obs.nsg_flow_logs_total as number) ?? 0;
        }

        // Metrics
        const nm = sub.network_metrics as Record<string, unknown> | null | undefined;
        if (nm && !nm.collection_error && Array.isArray(nm.gateway_metrics) && (nm.gateway_metrics as unknown[]).length > 0) {
          metricsCollected = true;
        }
      }

      topologySummary = {
        vnets, subnets, firewalls, appGateways, dnsZones, expressRoutes,
        workload: { vmCount, acaCount, aksCount, fnCount },
        bgp: { gatewaysWithBgp, peersConnected, peersDisconnected, routesLearned },
        observability: { networkWatchers, logWorkspaces, nsgFlowLogsEnabled, nsgTotal },
        metricsCollected,
      };
    } catch {
      // ignore topology parse errors
    }
  }

  // Findings breakdown by severity (non-AI, COMPLETED jobs only)
  let findingsBySeverity: { severity: string; count: number }[] = [];
  if (job.status === "COMPLETED") {
    const groups = await prisma.finding.groupBy({
      by: ["severity"],
      where: { engagementId: job.engagementId, aiGenerated: false },
      _count: { id: true },
    });
    findingsBySeverity = groups.map((g) => ({ severity: g.severity, count: g._count.id }));
  }

  const payload = {
    id: job.id,
    status: job.status,
    startedAt: job.startedAt,
    completedAt: job.completedAt,
    findingsCount: job.findingsCount,
    errorMessage: job.errorMessage,
    progressLog: job.progressLog,
    updatedAt: job.updatedAt,
    topologySummary,
    findingsBySeverity,
  };

  // Active jobs: allow brief CDN/browser caching (5s) to reduce polling pressure.
  // Terminal states (COMPLETED/FAILED): no-store so the UI always reads final state.
  const cacheControl =
    job.status === "COMPLETED" || job.status === "FAILED"
      ? "no-store"
      : "public, max-age=5, stale-while-revalidate=10";

  return NextResponse.json(payload, {
    headers: { "Cache-Control": cacheControl },
  });
}
