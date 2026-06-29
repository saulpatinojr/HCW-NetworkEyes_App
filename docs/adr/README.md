# Architecture Decision Records (ADRs)

This folder holds Architecture Decision Records for the CNA platform. The wider
in-repo `docs/` tree was migrated to the GitHub Wiki, but ADRs live **with the
code** so they are reviewed in the same pull request as the change they describe.

## Format

We use a lightweight [MADR](https://adr.github.io/madr/)-style template:

- **Status** — Proposed | Accepted | Superseded by ADR-XXXX
- **Context** — the forces at play; what made a decision necessary
- **Decision** — what we chose
- **Consequences** — the resulting trade-offs (good and bad)
- **Alternatives considered** — options we rejected, and why

Number ADRs sequentially (`NNNN-short-kebab-title.md`). Never edit an accepted
ADR's decision after the fact — supersede it with a new ADR and update the
`Status` line of the old one.

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-remove-anthropic-foundry-claude-path.md) | Remove the Anthropic / Foundry-Claude inference path | Accepted |
| [0002](0002-remove-foundry-private-access-smoke-test.md) | Remove the Foundry private-access smoke test | Accepted |
| [0003](0003-entra-redirect-uri-management.md) | Manage the NextAuth redirect URI in bootstrap, not the deploy | Accepted |
| [0004](0004-key-vault-network-hardening.md) | Key Vault network hardening (private-endpoint-only target) | Accepted |
| [0005](0005-container-image-pull-strategy.md) | Container image pull: Docker Hub now, ACR + managed identity later | Accepted |
