# Platform Footprint Review — June 2026

Recommendations only — no infrastructure changes have been applied. Each item requires explicit approval before a Terraform change. Cost figures are list-price estimates [VERIFY].

## Principle held during the encyclopedia build

Phases A–G added **zero new Azure resources and zero new containers**: the metrics and chat endpoints are routers inside the existing `ca-cna-api`, encyclopedia generation runs through the existing deliverables server-action path, and all new tables live in the existing PostgreSQL server. Deploys for this work need only workflow `030-build-images` + `012-fast-redeploy` — no Terraform apply.

## Current monthly estimate (list price)

| Environment | Minimal usage | With active AI usage |
|---|---|---|
| Dev | ~$415–450 | ~$515–550+ |
| Prod | ~$525–650 | ~$625–750+ |

Largest fixed drivers: PostgreSQL GP_Standard_D2s_v3 (~$199/mo **per env**), Front Door **Premium** + WAF (~$200/mo base **per env**).

## Recommendations (ranked by savings)

1. **Dev Front Door: Premium → Standard, or remove** (`providers/azure/security/main.tf:122`)
   ~$180/mo saving. Dev runs the same Premium Front Door + WAF as prod. Standard (~$20/mo) drops the managed WAF — acceptable for an internal dev endpoint; alternatively remove dev Front Door entirely and use Container App ingress with IP restrictions.
2. **Dev PostgreSQL: GP_Standard_D2s_v3 → B_Standard_B1ms** (`environments/azure/dev/main.tf:269`)
   ~$145/mo saving. Dev currently runs the identical prod-grade SKU and geo-redundant backups; burstable + local-redundant backup is sufficient for an ephemeral environment.
3. **Dev ephemerality cadence**
   Dev is documented as destroy/recreate-safe. Adopting destroy-when-idle (workflow 031) eliminates the entire dev base (~$415/mo) outside active development windows. Scale-to-zero is already enabled for dev Container Apps — the database and Front Door are the always-on remainder.
4. **Prod PostgreSQL right-sizing review**
   GP_Standard_D2s_v3 (2 vCore/8 GB) may exceed current load. Review actual CPU/memory metrics; D2ds_v4/B2ms could halve the ~$199/mo if utilization stays low. Needs a metrics check before any change.
5. **AI cost guardrails (both envs)**
   Foundry Claude usage is unmetered in Terraform — no quotas or cost alerts. With the new copilot endpoint, add an Azure Monitor cost/budget alert and consider per-engagement request limits (the chat endpoint already rate-limit-able at the web proxy).
6. **Prod Container Apps max replicas**
   `max_replicas = 3` across all three apps; if observed traffic never scales past 1, capping at 2 trims burst exposure. Low impact (~10–20% of the $70–90/mo baseline).

Already good (no action): dev scale-to-zero enabled; storage lifecycle tiering (Hot→Cool→delete at 365d); single Foundry account per env at S0; no Bastion/NAT idle resources; private endpoints minimal (2/env).
