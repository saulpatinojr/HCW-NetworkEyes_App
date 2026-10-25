#!/usr/bin/env bash
# Find the image 200-build-images.yml built, scanned and tagged for a commit, for 310-release-version.yml.
#
#   scripts/ci/find_release_image.sh            (configured by the environment below; run inside a full checkout)
#
# 200 tags `sha-<7>` on the CLI image only after every image passed Docker Scout, so that tag existing is the scan
# gate. The commit to release (TARGET_SHA, default GITHUB_SHA) is not always a commit 200 built: a commit that
# changes only documentation, tests or another workflow touches nothing 200 builds from, so the path filter gives
# it no 200 run of its own. So the search walks the first-parent history from the target to the NEAREST commit
# that has a 200 run whose `sha-<7>` tag exists in the registry. If that commit is not the target, the files
# changed between the two must touch none of 200's `on.push.paths` (scripts/ci/paths_touch_build.py); otherwise
# the release is refused with the files named, because the tagged commit contains code the found image was not
# built from.
#
# A 200 run of a commit that is still in progress is waited for (FIND_WAIT_SECONDS, default 1500); a run that has
# finished without the tag (scan failed, publishing off, a rehearsal, tag pruned by 370) is skipped and the search
# goes on to older commits, where the path check then decides.
#
# Environment (all required unless a default is shown):
#   GITHUB_REPOSITORY, GITHUB_SHA or TARGET_SHA, DOCKERHUB_NAMESPACE, IMAGE_REPOSITORY
#   REGISTRY (docker.io), WORKFLOW_FILE (.github/workflows/200-build-images.yml),
#   FIND_WAIT_SECONDS (1500), FIND_POLL_SECONDS (30), FIND_MAX_COMMITS (100), GITHUB_OUTPUT (when set, the results are appended to it; always printed too)
# Needs: git, gh (with GH_TOKEN), jq, docker buildx, python3.
# Output: digest, build_commit, run_ids (space separated ids of the 200 runs of that commit), tag.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/registry_digest.sh
source "$HERE/registry_digest.sh"

REGISTRY="${REGISTRY:-docker.io}"
WORKFLOW_FILE="${WORKFLOW_FILE:-.github/workflows/200-build-images.yml}"
WAIT="${FIND_WAIT_SECONDS:-1500}"
POLL="${FIND_POLL_SECONDS:-30}"
MAX_COMMITS="${FIND_MAX_COMMITS:-100}"
TARGET="${TARGET_SHA:-${GITHUB_SHA:-}}"
for v in GITHUB_REPOSITORY DOCKERHUB_NAMESPACE IMAGE_REPOSITORY; do
  if [ -z "${!v:-}" ]; then
    echo "::error::${v} is not set." >&2
    exit 1
  fi
done
if ! [[ "$TARGET" =~ ^[0-9a-f]{40}$ ]]; then
  echo "::error::The commit to release must be a full 40-character SHA (got '${TARGET}')." >&2
  exit 1
fi
IMAGE="${REGISTRY}/${DOCKERHUB_NAMESPACE}/${IMAGE_REPOSITORY}"
WORKFLOW_NAME="$(basename "$WORKFLOW_FILE")"

no_build_message() {
  echo "::error::No run of ${WORKFLOW_NAME} built an image for commit ${TARGET} or an earlier commit of its history${1:+ ($1)}. Tag a commit that 200 built (the successful runs of ${WORKFLOW_NAME} are listed in Actions, and each one's step summary lists the digests it published), or run 200 on ${TARGET} first (Actions, Run workflow), then re-run this release." >&2
}

mapfile -t CHAIN < <(git rev-list --first-parent -n "$MAX_COMMITS" "$TARGET")
[ "${#CHAIN[@]}" -gt 0 ] || { echo "::error::git has no history for ${TARGET}; the checkout needs fetch-depth: 0." >&2; exit 1; }

DEADLINE=$((SECONDS + WAIT))
BUILD_COMMIT="" DIGEST="" RUN_IDS=""
while :; do
  RUNS="$(gh run list --repo "$GITHUB_REPOSITORY" --workflow "$WORKFLOW_NAME" --limit 200 --json databaseId,headSha,status,conclusion,url)"
  PENDING="" SKIPPED=()
  for COMMIT in "${CHAIN[@]}"; do
    ROWS="$(jq -c --arg c "$COMMIT" '[.[] | select(.headSha == $c)]' <<< "$RUNS")"
    [ "$(jq 'length' <<< "$ROWS")" -gt 0 ] || continue
    TAG="sha-${COMMIT:0:7}"
    rc=0
    FOUND_DIGEST="$(registry_digest "${IMAGE}:${TAG}")" || rc=$?
    if [ "$rc" -eq 0 ]; then
      BUILD_COMMIT="$COMMIT" DIGEST="$FOUND_DIGEST"
      RUN_IDS="$(jq -r '[.[].databaseId | tostring] | join(" ")' <<< "$ROWS")"
      break
    fi
    if [ "$rc" -ne 1 ]; then
      echo "::error::Could not ask the registry whether ${IMAGE}:${TAG} exists (see the message above); refusing to guess." >&2
      exit 1
    fi
    if [ "$(jq '[.[] | select(.status != "completed")] | length' <<< "$ROWS")" -gt 0 ]; then
      PENDING="$COMMIT"
      break
    fi
    SKIPPED+=("${COMMIT:0:7}")
  done
  [ -z "$BUILD_COMMIT" ] || break
  if [ -n "$PENDING" ]; then
    if [ "$SECONDS" -ge "$DEADLINE" ]; then
      echo "::error::Waited ${WAIT} s for ${WORKFLOW_NAME} to tag ${IMAGE}:sha-${PENDING:0:7}; re-run this release when it has finished." >&2
      exit 1
    fi
    echo "${WORKFLOW_NAME} is still building ${PENDING:0:7}; waiting ${POLL} s for ${IMAGE}:sha-${PENDING:0:7}"
    sleep "$POLL"
    continue
  fi
  no_build_message "${SKIPPED[*]:+runs of ${SKIPPED[*]} finished without the sha tag}"
  exit 1
done

if [ "$BUILD_COMMIT" != "$TARGET" ]; then
  CHANGED="$(git diff --name-only "$BUILD_COMMIT" "$TARGET")"
  OFFENDING=""
  rc=0
  OFFENDING="$(python3 "$HERE/paths_touch_build.py" "$WORKFLOW_FILE" <<< "$CHANGED")" || rc=$?
  if [ "$rc" -ne 0 ]; then
    if [ "$rc" -eq 1 ]; then
      WHY="No run of ${WORKFLOW_NAME} exists for commit ${TARGET}, and"
      for short in "${SKIPPED[@]:-}"; do
        if [ "$short" = "${TARGET:0:7}" ]; then
          WHY="The ${WORKFLOW_NAME} run for commit ${TARGET} finished without the sha tag (its scan or build failed, publishing was off, or 370 pruned the tag), and"
        fi
      done
      echo "::error::${WHY} it changes files ${WORKFLOW_NAME} builds from since the last built commit ${BUILD_COMMIT} ($(tr '\n' ' ' <<< "$OFFENDING")). Tag the commit that 200 built (${BUILD_COMMIT} is the nearest one), or run 200 on ${TARGET} first." >&2
    else
      echo "::error::Could not read the paths ${WORKFLOW_NAME} builds from (exit ${rc})." >&2
    fi
    exit 1
  fi
  echo "Commit ${TARGET:0:7} has no ${WORKFLOW_NAME} run of its own; its image is the one built from ${BUILD_COMMIT:0:7}, and nothing changed since that ${WORKFLOW_NAME} builds from ($(tr '\n' ' ' <<< "$CHANGED"))."
fi

echo "Found ${IMAGE}:sha-${BUILD_COMMIT:0:7} = ${DIGEST} (built from ${BUILD_COMMIT}, ${WORKFLOW_NAME} runs: ${RUN_IDS})"
emit() {
  printf '%s=%s\n' "$1" "$2"
  if [ -n "${GITHUB_OUTPUT:-}" ]; then printf '%s=%s\n' "$1" "$2" >> "$GITHUB_OUTPUT"; fi
}
emit digest "$DIGEST"
emit build_commit "$BUILD_COMMIT"
emit run_ids "$RUN_IDS"
emit tag "sha-${BUILD_COMMIT:0:7}"
