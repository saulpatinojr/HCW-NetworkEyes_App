#!/usr/bin/env bash
# Verify that one published image digest was signed, and its SLSA provenance attested, by
# 200-build-images.yml of this repository on main (scripts/ci/sign_image.sh is the signing side).
# Called by 310-release-version.yml before it gives an already-scanned digest a release tag:
#
#   IMAGE_REPOSITORY=<repository> scripts/ci/verify_signed_digest.sh docker.io/<namespace>/<repository>@sha256:<64>
#
# The checks are the ones the appliances make before a deploy (their
# scripts/ci/verify_image_signature.sh): keyless signature and provenance attestation under this
# repository's 200 workflow identity, issued by GitHub's OIDC provider, on exactly this digest.
# cosign 3 accepts one proof of signing time per verification (a signed timestamp from the TSA, or
# Rekor's integrated timestamp), so each verification tries the TSA form first and then the
# integrated one; identity, issuer and transparency-log inclusion are enforced on both.
# IMAGE_REPOSITORY is the one repository this repository publishes to (see sign_image.sh).
set -euo pipefail

REF="${1:-}"
if ! [[ "${IMAGE_REPOSITORY:-}" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
  echo "::error::IMAGE_REPOSITORY must name the Docker Hub repository (lowercase letters, digits and hyphens; got '${IMAGE_REPOSITORY:-}')." >&2
  exit 1
fi
if ! [[ "$REF" =~ ^docker\.io/[a-z0-9][a-z0-9._-]*/${IMAGE_REPOSITORY}@sha256:([0-9a-f]{64})$ ]]; then
  echo "::error::verify_signed_digest.sh expects a digest reference docker.io/<namespace>/${IMAGE_REPOSITORY}@sha256:<64> (got '${REF}')." >&2
  exit 1
fi
DIGEST="sha256:${BASH_REMATCH[1]}"
for v in GITHUB_SERVER_URL GITHUB_REPOSITORY; do
  if [ -z "${!v:-}" ]; then
    echo "::error::${v} is not set; verify_signed_digest.sh runs inside GitHub Actions only." >&2
    exit 1
  fi
done
IDENTITY="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/.github/workflows/200-build-images.yml@refs/heads/main"
ISSUER="https://token.actions.githubusercontent.com"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cosign_with_either_timestamp() {
  local out="$1"; shift
  if cosign "$@" --use-signed-timestamps > "$out" 2> "$WORK/stderr.tsa"; then
    return 0
  fi
  if cosign "$@" > "$out" 2> "$WORK/stderr.tlog"; then
    return 0
  fi
  echo "::error::cosign ${1} failed for ${REF} with both timestamp policies; the digest is not signed by ${IDENTITY}." >&2
  echo "--- --use-signed-timestamps:" >&2; cat "$WORK/stderr.tsa" >&2
  echo "--- integrated timestamp:" >&2; cat "$WORK/stderr.tlog" >&2
  return 1
}

echo "Verifying the signature on ${REF}"
cosign_with_either_timestamp "$WORK/signatures.json" verify \
  --certificate-identity "$IDENTITY" \
  --certificate-oidc-issuer "$ISSUER" \
  --output json "$REF"
if ! jq -e --arg d "$DIGEST" \
     'type == "array" and length >= 1 and all(.[]; .critical.image["docker-manifest-digest"] == $d)' \
     "$WORK/signatures.json" > /dev/null; then
  echo "::error::cosign reported no signature on exactly ${DIGEST}." >&2
  exit 1
fi

echo "Verifying the SLSA provenance attestation on ${REF}"
cosign_with_either_timestamp "$WORK/attestations.jsonl" verify-attestation \
  --type slsaprovenance02 \
  --certificate-identity "$IDENTITY" \
  --certificate-oidc-issuer "$ISSUER" \
  "$REF"
if ! [ -s "$WORK/attestations.jsonl" ]; then
  echo "::error::cosign reported no provenance attestation for ${REF}." >&2
  exit 1
fi
echo "Verified ${REF}: signed and attested by ${IDENTITY}"
