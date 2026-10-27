# Documentation (`docs/`)

This folder is the one home for the long-form documentation of NetworkEyes: guides, architecture write-ups, runbooks
(step-by-step procedures) and decision records (a short note saying what was decided, by whom, and why). The short
documents that every repository has stay at the root. The full list, and the rule that decides what is allowed where,
is in the [Documentation map](../README.md#documentation-map) of the main `README.md`, which is the only place the rule
is written out.

**There are no pages here yet.** The GitHub Wiki that used to hold this material was deleted on 2026-10-27, and the
owner chose this folder as its replacement (`REVIEW.md`, R-031). Which of the old pages come back is still the owner's
decision, so nothing has been copied in. Do not restore a page on your own initiative.

## What belongs here

- Guides, architecture descriptions, runbooks and decision records that are too long for `README.md`, `CHANGELOG.md`,
  `REVIEW.md` or `TODO.md`.
- Documents at any depth below this folder, for example `docs/runbooks/` or `docs/decisions/`. Nothing is required to
  exist.

## What does not belong here

- A fact that already has a home. The list of settings is `.env.example`, completed work is `CHANGELOG.md`, open work
  is `TODO.md`, and anything that needs the owner is `REVIEW.md`. Link to them instead of copying them, because two
  copies drift apart.
- Secrets, tokens, keys, tenant or subscription identifiers, personal data, data from a real environment or real
  network topology.
- A page named `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SUPPORT.md`, `FUNDING.md` or
  `PULL_REQUEST_TEMPLATE.md` (in any letter case), or a folder named `ISSUE_TEMPLATE` or `PULL_REQUEST_TEMPLATE`,
  directly in this folder. GitHub reads those names from `docs/` as well as from `.github/`, so a copy here would be a
  second policy that GitHub may show. Those files live in `.github/` only.

## Rules

1. **Review.** A document here is reviewed in a pull request like code, and `CHANGELOG.md` records the change when a
   reader would notice it.
2. **The location is checked by a program.** `scripts/validate_documentation_model.py` runs in CI and fails the build
   when a document file sits where the Documentation map does not allow one. Inside this folder it accepts every kind
   of document file it knows (`.md`, `.rst`, `.adoc` and the like) at any depth. It refuses the same files in a folder
   named `doc`, `Docs` or `documentation`, and in a `docs` folder that is not at the top of the repository (`src/docs/`,
   for example): the repository has one home for documentation.
3. **Format and names.** Write Markdown, in a file whose name ends in `.md`, with lowercase words joined by hyphens
   (for example `docs/runbooks/rotate-the-registry-token.md`). This index is the one exception, because GitHub shows a
   folder's `README.md` under its file list. The format and the names are a convention and are not checked.
4. **Owner and review date.** The repository owner owns this folder. Last reviewed: 2026-10-27.

## What else is in this folder

`roles/` is not documentation. It holds the custom Azure role definition as a JSON data file
(`roles/network-assessment-bgp-reader.json`). The application's help screen, `.env.example` and the module manifest
point at that exact path, so do not move or rename it.
