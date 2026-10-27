# Security policy

## Reporting a vulnerability

Please report a suspected vulnerability privately, not in a public issue.

1. Open <https://github.com/saulpatinojr/HCW-NetworkEyes_App/security/advisories/new> (or go to the repository's
   **Security** tab and choose **Report a vulnerability**).
2. Describe what you found. Only the maintainers and you can see the report.

Do not put exploit details, credentials, tokens, private endpoints, tenant or subscription identifiers, personal data or
data from a real environment in a public issue, a pull request, a comment or a commit message. If the private form is not available to
you, open a minimal public issue that asks for a secure contact and says nothing about the problem itself. Only test
systems and data you own or are explicitly allowed to assess.

When it is safe to do so, please include:

- the affected version, branch, image tag or commit, and the component (see the scope list below);
- the impact and any preconditions, in plain words;
- steps to reproduce, or a minimal proof of concept with sensitive values removed;
- sanitized logs, traces or screenshots; and
- any workaround you know of, and a disclosure date if you have one in mind.

## What this repository is, and what is in scope

This repository is the product code of NetworkEyes: the web app (`apps/cna-web`),
the API (`apps/cna-api`), the worker (`apps/cna-worker`), the `cna` Python package, the Azure network engine package
(`packages/cna-azure-network-engine`), the container images built from them, and the workflows in `.github/` that build
and publish those images. Please report problems in:

- authentication, sign-in and session handling, authorization and role checks, and the internal bearer
  (`CNA_API_TOKEN`) that protects service-to-service routes such as `/api/drawio-mcp/*`;
- the handling of cloud credentials and of the administrator-entered AI provider keys (encrypted with AES-256-GCM,
  never to be logged, returned or stored anywhere else);
- the delivery portal, report and diagram generation, file upload and export paths;
- the images, their base images and dependencies, and the image signature and provenance chain (cosign signatures and
  the SLSA attestation published with every image digest);
- the workflows, actions, release automation and artifact handling in `.github/`; and
- examples, tests, fixtures and documentation that expose a secret or sensitive data.

Out of scope here, with where to report it instead:

- Deployment, Terraform and runtime problems of an environment that runs these images belong to whoever deploys
  and operates that environment. Report a flaw in an image itself here.
- The free upload-only lab build,
  [HCW-NetworkEyes_AddOn](https://github.com/saulpatinojr/HCW-NetworkEyes_AddOn), has its own repository and policy.
- Problems already recorded in this repository's `REVIEW.md` or `TODO.md` do not need a new report unless you found a
  missing control, a wider impact or a way around the recorded mitigation.

## If you find a secret

Treat any secret in a commit, issue, log, artifact or document as disclosed. Tell the maintainers privately (use the
form above), keep only the minimum evidence, and do not try to use it. The maintainers rotate or revoke the value.

## What happens next

Reports are read and triaged as soon as practical. How long a fix takes depends on severity, the versions affected and
who has to change what (this repository or an upstream project). Please keep the report
private until the maintainers confirm that disclosure is coordinated. Credit is given in the advisory if you want it.

This is a one-maintainer project: the maintainer is the repository owner named in `.github/CODEOWNERS`, and no response
time is promised.

## Supported versions

| Version or branch | Supported |
| --- | --- |
| `main` | Yes |
| The newest published image tags (`<role>-sha-<7>` and `*-latest`) and the newest `v*` / `engine-v*` release | Yes |
| Earlier releases and earlier image tags | No; update to the newest one |
