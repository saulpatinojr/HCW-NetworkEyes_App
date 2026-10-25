#!/usr/bin/env bash
# Run the container and workflow checks locally, with the same pinned tools CI uses (ticket #253).
#
# What it needs: Docker and bash. On Windows that is Docker Desktop (Linux containers, context `desktop-linux`) and
# Git Bash; start it from PowerShell with `bash scripts/ci/local-container-checks.sh all`. Nothing else is installed.
#
# Usage:   bash scripts/ci/local-container-checks.sh <check>...
#   hadolint       lint every tracked Dockerfile with .hadolint.yaml (the CI job "Dockerfile Lint (hadolint)")
#   actionlint     lint every workflow in .github/workflows (the CI job "Workflow Lint (actionlint)")
#   trivy-config   Trivy configuration scan: Dockerfiles, docker-compose.yml, infra/ (misconfigurations)
#   trivy-fs       Trivy filesystem scan: locked dependencies (uv.lock, package-lock.json) and secrets
#   trivy-image <image>   Trivy scan of an image that is already in the local image store, for example one you
#                         built with `docker build -t cna:test .`; it is exported to a tar file and scanned from
#                         there, so no Docker socket is ever mounted into a container
#   all            hadolint, actionlint, trivy-config and trivy-fs
#
# Settings (environment variables):
#   TRIVY_SEVERITY   severities Trivy reports (default HIGH,CRITICAL)
#   TRIVY_EXIT_CODE  exit code Trivy returns when it finds something (default 1; use 0 to only report)
#   TRIVY_IGNORE_UNFIXED  trivy-image reports only findings that have a fix (default 1, like CI); 0 lists all
#   CNA_CHECKS_ANY_CONTEXT=1   allow a Docker context other than desktop-linux or default (see below)
#
# How it stays safe: every tool runs in a disposable container (--rm) with all capabilities dropped, no privilege
# escalation and no Docker socket. The repository is mounted read-only. hadolint and actionlint get no network.
# Trivy gets network access to download its vulnerability database into a named volume, `cna-trivy-cache`, which is
# the only thing this script leaves behind; remove it with `docker volume rm cna-trivy-cache`.
#
# The script stops when `docker context show` names an engine other than your own machine (desktop-linux, or
# default on Linux), or when DOCKER_HOST is set, because a scan against a shared or remote engine is a different
# decision. Set CNA_CHECKS_ANY_CONTEXT=1 only when you mean it.
#
# Where the versions come from: each is the newest stable release on the date in the comment, taken from the
# project's GitHub releases page, pulled by tag and pinned by the digest the registry reported. 300-test-codebase.yml
# pins hadolint and actionlint to the same digests and tests/unit/test_ci_hygiene.py fails if the two drift apart.
# To move a pin: pull the new tag, copy the digest Docker prints, change it here and in the workflow together.

set -euo pipefail

# hadolint 2.15.1 (released 2026-07-31) https://github.com/hadolint/hadolint/releases
HADOLINT_IMAGE="ghcr.io/hadolint/hadolint:v2.15.1@sha256:32dac94127fd60b7b7e3fbfc65e1383b9b5e25c9bfd7b8536de7a539fe68a12d"
# actionlint 1.7.12 (released 2026-03-30) https://github.com/rhysd/actionlint/releases
ACTIONLINT_IMAGE="rhysd/actionlint:1.7.12@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667"
# Trivy 0.76.1 (released 2026-10-21) https://github.com/aquasecurity/trivy/releases. Never use a tag alone and never
# `latest`: on 2026-03-19 and 2026-03-22 malicious Trivy images were published under moving tags
# (GHSA-69fq-xp46-6x23); a digest cannot be moved. 0.72.0 or later is required for the plugin path-traversal fix.
TRIVY_IMAGE="ghcr.io/aquasecurity/trivy:0.76.1@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c"
TRIVY_CACHE_VOLUME="cna-trivy-cache"
# Scratch directory (inside the repository, ignored by git) where trivy-image writes the exported image tar.
SCRATCH_DIR=".trivy-image-scratch"

TRIVY_SEVERITY="${TRIVY_SEVERITY:-HIGH,CRITICAL}"
TRIVY_EXIT_CODE="${TRIVY_EXIT_CODE:-1}"

# Git Bash rewrites paths that look like Unix paths before handing them to docker.exe; switch that off, and use the
# Windows form of the repository path (pwd -W exists only in Git Bash) so Docker Desktop can mount it.
export MSYS_NO_PATHCONV=1
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
if REPO="$(pwd -W 2>/dev/null)"; then :; else REPO="$(pwd)"; fi

say() { printf '%s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 2; }

command -v docker >/dev/null 2>&1 || fail "docker was not found on PATH. Start Docker Desktop and try again."
context="$(docker context show 2>/dev/null || true)"
say "Docker context: ${context:-unknown}"
if [ "${CNA_CHECKS_ANY_CONTEXT:-0}" != "1" ]; then
  case "$context" in
    desktop-linux | default) ;;
    *) fail "Docker context '$context' is not desktop-linux or default. Switch with 'docker context use desktop-linux', or set CNA_CHECKS_ANY_CONTEXT=1 if you really mean this engine." ;;
  esac
  [ -z "${DOCKER_HOST:-}" ] || fail "DOCKER_HOST is set ($DOCKER_HOST); unset it, or set CNA_CHECKS_ANY_CONTEXT=1 if you really mean that engine."
fi
docker info >/dev/null 2>&1 || fail "the Docker engine does not answer. Start Docker Desktop and try again."

# Flags every tool container gets: one definition, shared with the CI jobs (scripts/ci/harden-flags.sh).
# shellcheck source=scripts/ci/harden-flags.sh
source ./scripts/ci/harden-flags.sh

results=()
overall=0
record() { # name exit-code
  if [ "$2" -eq 0 ]; then results+=("PASS  $1"); else results+=("FAIL  $1 (exit $2)"); overall=1; fi
}

run_hadolint() {
  local files
  mapfile -t files < <(git ls-files -- 'Dockerfile' '*/Dockerfile')
  [ "${#files[@]}" -gt 0 ] || fail "no Dockerfile is tracked in this repository"
  say "== hadolint on: ${files[*]}"
  local code=0
  docker run "${HARDEN[@]}" --network none -v "$REPO:/work:ro" -w /work "$HADOLINT_IMAGE" \
    hadolint --config .hadolint.yaml --no-color "${files[@]}" || code=$?
  record "hadolint (${#files[@]} Dockerfiles)" "$code"
}

run_actionlint() {
  say "== actionlint on .github/workflows/*.yml"
  local code=0
  docker run "${HARDEN[@]}" --network none -v "$REPO:/repo:ro" -w /repo "$ACTIONLINT_IMAGE" \
    -color=false .github/workflows/*.yml || code=$?
  record "actionlint" "$code"
}

# Trivy keeps its database in a named volume so repeated runs are quick; /tmp is a throwaway tmpfs.
trivy() {
  docker run "${HARDEN[@]}" --tmpfs /tmp -v "$TRIVY_CACHE_VOLUME:/root/.cache" "$@"
}

run_trivy_config() {
  say "== trivy config (severity $TRIVY_SEVERITY)"
  local code=0
  trivy -v "$REPO:/work:ro" -w /work "$TRIVY_IMAGE" \
    config --severity "$TRIVY_SEVERITY" --exit-code "$TRIVY_EXIT_CODE" --skip-dirs .git,node_modules,.venv,local . || code=$?
  record "trivy config" "$code"
}

run_trivy_fs() {
  say "== trivy fs: vulnerabilities in lockfiles and secrets (severity $TRIVY_SEVERITY)"
  local code=0
  trivy -v "$REPO:/work:ro" -w /work "$TRIVY_IMAGE" \
    fs --no-progress --include-dev-deps --scanners vuln,secret --severity "$TRIVY_SEVERITY" --exit-code "$TRIVY_EXIT_CODE" \
    --skip-dirs .git,node_modules,.venv,local . || code=$?
  record "trivy fs" "$code"
}

run_trivy_image() {
  local image="${1:-}"
  [ -n "$image" ] || fail "trivy-image needs an image name, for example: trivy-image cna:test"
  docker image inspect "$image" >/dev/null 2>&1 || fail "image '$image' is not in the local image store"
  say "== trivy image $image (severity $TRIVY_SEVERITY)"
  # Export to a tar file inside a scratch directory of the repository, scan from there, delete it afterwards.
  local code=0
  mkdir -p "$SCRATCH_DIR"
  trap 'rm -rf "$SCRATCH_DIR"' EXIT
  docker save "$image" -o "$SCRATCH_DIR/image.tar"
  # The same policy as the `Image Scan (Trivy)` job of 300-test-codebase.yml and the Docker Scout gate of
  # 200-build-images.yml: fixable findings only, and the narrow suppressions of .trivyignore.yaml (each has its
  # reason there). Set TRIVY_IGNORE_UNFIXED=0 to list the findings that have no fix as well.
  local unfixed=()
  [ "${TRIVY_IGNORE_UNFIXED:-1}" = "0" ] || unfixed=(--ignore-unfixed)
  trivy -v "$REPO/$SCRATCH_DIR:/scan:ro" -v "$REPO:/work:ro" "$TRIVY_IMAGE" \
    image --no-progress --input /scan/image.tar --severity "$TRIVY_SEVERITY" ${unfixed[@]+"${unfixed[@]}"} \
    --ignorefile /work/.trivyignore.yaml --exit-code "$TRIVY_EXIT_CODE" || code=$?
  rm -rf "$SCRATCH_DIR"
  record "trivy image $image" "$code"
}

[ "$#" -gt 0 ] || fail "name a check: hadolint, actionlint, trivy-config, trivy-fs, trivy-image <image>, or all"
while [ "$#" -gt 0 ]; do
  case "$1" in
    hadolint) run_hadolint ;;
    actionlint) run_actionlint ;;
    trivy-config) run_trivy_config ;;
    trivy-fs) run_trivy_fs ;;
    trivy-image) shift; run_trivy_image "${1:-}" ;;
    all) run_hadolint; run_actionlint; run_trivy_config; run_trivy_fs ;;
    *) fail "unknown check '$1'" ;;
  esac
  shift
done

say ""
say "Summary"
printf '  %s\n' "${results[@]}"
exit "$overall"
