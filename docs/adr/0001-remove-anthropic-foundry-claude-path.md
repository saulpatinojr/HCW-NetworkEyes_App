# 0001 — Remove the Anthropic / Foundry-Claude inference path

- **Status:** Accepted (2026-06-29)
- **Deciders:** CNA platform
- **Related:** issues #98, #99, #100; [ADR-0002](0002-remove-foundry-private-access-smoke-test.md)

## Context

CNA shipped two GenAI engines behind a switch: `azure-openai` and `foundry-claude`
(an Anthropic Messages-compatible deployment on the Azure AI Foundry / AIServices
account). The `foundry-claude` path is **dead in this tenant**:

- `az cognitiveservices account deployment list` on `cna-dev-eus2-aif2` returns **no
  Anthropic model**. The `/anthropic/v1/messages` endpoint has nothing behind it.
- Azure OpenAI (`gpt-chat-latest`) was already made the default engine (commit
  `1b5dbdc`), leaving the Claude wiring inert.
- The dead path created real friction: the Anthropic Key Vault secret tripped an ALZ
  Key Vault guardrail (403), and the post-deploy smoke test burned time validating an
  endpoint that could never succeed.

Carrying inert provider code adds surface area (a second wire format, an API-key
fallback branch, extra env vars and Terraform variables/outputs) with zero benefit.

## Decision

Remove the `foundry-claude` engine end-to-end and make **Azure OpenAI the only
supported engine**:

- **Terraform** — drop the `foundry_claude_endpoint` / `foundry_claude_model`
  variables and the `FOUNDRY_CLAUDE_*` container env vars (dev + prod workload);
  delete the `foundry_claude_messages_endpoint` output from the AI module and the
  workloads; constrain `ai_engine_default` validation to `["azure-openai"]`. The
  firewall egress FQDN is now derived from `var.azure_openai_endpoint` instead of the
  deleted Claude output.
- **Web** (`apps/cna-web/lib/ai-engine.ts`) — collapse `AiEngineId` to
  `"azure-openai"`; remove the Claude status entry, `getFoundryAuthHeaders`,
  `toClaudeMessages`, and `completeWithClaude`.
- **API** (`cna/ai_engine/chat_agent.py`) — remove `ENGINE_FOUNDRY_CLAUDE`,
  `DEFAULT_CLAUDE_MODEL`, and `_complete_claude`.
- **Config/docs** — `.env.example`, `README.md`, the bootstrap script, and the
  drift/sync workflows lose all `FOUNDRY_CLAUDE_*` references.

The Foundry / AIServices **account and project are kept** — Azure OpenAI rides the
same account and shares its private endpoint.

## Consequences

- **Good:** one wire format, one auth model (managed identity; local auth disabled on
  the account), smaller config surface, no dead guardrail trips.
- **Good:** grounds the LLM path in the actually-deployed provider, per repo guidance
  to base provider choices on the deployed reality, not memory.
- **Trade-off:** re-introducing Claude later means restoring the engine abstraction.
  Acceptable — it can be added back behind the same `AiEngineId` union if a Claude
  deployment ever lands in-tenant.
- The retired `foundry-claude` id is now rejected by `normalizeAiEngine` /
  `resolve_engine` and falls through to `azure-openai`; any stored `ai.activeEngine`
  setting of `foundry-claude` degrades gracefully to the default.

## Alternatives considered

- **Keep it inert behind UNUSED markers** (status quo) — rejected: ongoing
  maintenance and guardrail friction for a path that cannot work in this tenant.
- **Wait for a Claude-on-Foundry deployment** — rejected: no committed timeline, and
  the abstraction can be restored cheaply if/when that changes.
