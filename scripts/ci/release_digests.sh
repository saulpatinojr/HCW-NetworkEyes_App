#!/usr/bin/env bash
# Resolve and verify the other four images of the build 310-release-version.yml promotes, so that the release
# notes can list the digest of every image that build published, and so the release job can give each of the five its
# version tag (this script supplies the four besides the CLI image, whose digest find_release_image.sh found).
#
#   BUILD_COMMIT=<40-hex commit 200 built> RUN_IDS="<id> <id>" scripts/ci/release_digests.sh
#
# find_release_image.sh found the CLI image (`sha-<7>`) and verify_signed_digest.sh verified it. 200 attaches the
# tags of all five images in one job, after every image passed Docker Scout, so for the same commit the others carry
# `api-sha-<7>`, `worker-sha-<7>`, `web-sha-<7>` and `migrator-sha-<7>` (the prefixes are the `sha_prefix` values of
# 200-build-images.yml; tests/security/test_release_scripts_behaviour.py keeps the two in step). For each of them:
#   1. the tag must exist: a missing tag means the build did not publish a complete set, and the release stops;
#      "could not ask the registry" is a different answer and also stops it (registry_digest.sh);
#   2. its digest must verify exactly as the CLI digest did: signed and attested by 200 of this repository on main,
#      built by the workflow run RUN_IDS names (one run, attempts of it allowed), from BUILD_COMMIT
#      (scripts/ci/verify_signed_digest.sh). RUN_IDS is the run id of the builder of the CLI image's attestation
#      (the `builder_run_id` output of its verification), not every run of the commit: the five images of one
#      release then come from one build even when the commit was built more than once.
# Outputs (stdout, and GITHUB_OUTPUT when set): digest_api, digest_worker, digest_web, digest_migrator.
# Environment (all required): DOCKERHUB_NAMESPACE, IMAGE_REPOSITORY, BUILD_COMMIT, plus what verify_signed_digest.sh
# needs (GITHUB_SERVER_URL, GITHUB_REPOSITORY, cosign, docker buildx). REGISTRY defaults to docker.io.
# RUN_IDS is required: exactly one workflow run id.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/registry_digest.sh
source "$HERE/registry_digest.sh"

REGISTRY="${REGISTRY:-docker.io}"
for v in DOCKERHUB_NAMESPACE IMAGE_REPOSITORY BUILD_COMMIT; do
  if [ -z "${!v:-}" ]; then
    echo "::error::${v} is not set." >&2
    exit 1
  fi
done
if ! [[ "${RUN_IDS:-}" =~ ^[0-9]+$ ]]; then
  echo "::error::RUN_IDS must be the single run id of the build that made the CLI image (got '${RUN_IDS:-}')." >&2
  exit 1
fi
if ! [[ "$BUILD_COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
  echo "::error::BUILD_COMMIT must be a full 40-character SHA (got '${BUILD_COMMIT}')." >&2
  exit 1
fi
IMAGE="${REGISTRY}/${DOCKERHUB_NAMESPACE}/${IMAGE_REPOSITORY}"
SHORT="${BUILD_COMMIT:0:7}"

emit() {
  printf '%s=%s\n' "$1" "$2"
  if [ -n "${GITHUB_OUTPUT:-}" ]; then printf '%s=%s\n' "$1" "$2" >> "$GITHUB_OUTPUT"; fi
}

# component:tag prefix, as `sha_prefix` in 200-build-images.yml (build-images matrix) and the `type=sha,prefix=`
# lines of its build-web job.
for entry in api:api-sha- worker:worker-sha- web:web-sha- migrator:migrator-sha-; do
  component="${entry%%:*}"
  tag="${entry#*:}${SHORT}"
  rc=0
  digest="$(registry_digest "${IMAGE}:${tag}")" || rc=$?
  if [ "$rc" -eq 1 ]; then
    echo "::error::${IMAGE}:${tag} does not exist, so the build of ${BUILD_COMMIT} did not publish a complete set of images (200 tags all five together). Nothing is released from an incomplete build." >&2
    exit 1
  fi
  if [ "$rc" -ne 0 ]; then
    echo "::error::Could not ask the registry whether ${IMAGE}:${tag} exists (see the message above); refusing to guess." >&2
    exit 1
  fi
  if ! [[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    echo "::error::The registry answered '${digest}' for ${IMAGE}:${tag}, which is not a sha256 digest." >&2
    exit 1
  fi
  EXPECTED_REVISION="$BUILD_COMMIT" EXPECTED_RUN_IDS="$RUN_IDS" \
    bash "$HERE/verify_signed_digest.sh" "${IMAGE}@${digest}"
  emit "digest_${component}" "$digest"
done
