#!/usr/bin/env bash
# Verify that one published image digest was built, signed and attested by 200-build-images.yml of this repository
# on main, and (optionally) that it was built from a named commit. scripts/ci/sign_image.sh is the signing side.
# Called by 310-release-version.yml before it gives an already-scanned digest a release tag:
#
#   IMAGE_REPOSITORY=<repository> [EXPECTED_REVISION=<40-hex commit>] [EXPECTED_RUN_IDS="<id> <id>"] \
#     scripts/ci/verify_signed_digest.sh docker.io/<namespace>/<repository>@sha256:<64>
#
# Checks, all of which must pass:
#   1. cosign verify: a keyless signature on exactly this digest, under this repository's 200 workflow identity
#      (certificate identity .../.github/workflows/200-build-images.yml@refs/heads/main), issued by GitHub's OIDC
#      provider, in the transparency log;
#   2. cosign verify-attestation: a SLSA v0.2 provenance attestation under the same identity;
#   3. the provenance statement names this digest as its subject, and its `predicate.builder.id` is a run of this
#      repository (https://github.com/<repo>/actions/runs/<id>/...), one of EXPECTED_RUN_IDS when those are given
#      (the 200 runs of the commit the caller found). Checks 1-3 are what any consumer of the
#      image should make before it runs it (README, Verifying images);
#   4. when EXPECTED_REVISION is set: the image's `org.opencontainers.image.revision` label, which is part of the
#      signed digest, equals that commit, so the digest is bound to the commit and not only to the workflow.
# cosign 3 accepts one proof of signing time per verification (a signed timestamp from the TSA, or Rekor's
# integrated timestamp), so each verification tries the TSA form first and then the integrated one; identity,
# issuer and transparency-log inclusion are enforced on both.
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
DIGEST_HEX="${BASH_REMATCH[1]}"
DIGEST="sha256:${DIGEST_HEX}"
for v in GITHUB_SERVER_URL GITHUB_REPOSITORY; do
  if [ -z "${!v:-}" ]; then
    echo "::error::${v} is not set; verify_signed_digest.sh runs inside GitHub Actions only." >&2
    exit 1
  fi
done
EXPECTED_REVISION="${EXPECTED_REVISION:-}"
EXPECTED_RUN_IDS="${EXPECTED_RUN_IDS:-}"
if [ -n "$EXPECTED_REVISION" ] && ! [[ "$EXPECTED_REVISION" =~ ^[0-9a-f]{40}$ ]]; then
  echo "::error::EXPECTED_REVISION must be a full 40-character commit SHA (got '${EXPECTED_REVISION}')." >&2
  exit 1
fi
if [ -n "$EXPECTED_RUN_IDS" ] && ! [[ "$EXPECTED_RUN_IDS" =~ ^[0-9]+( [0-9]+)*$ ]]; then
  echo "::error::EXPECTED_RUN_IDS must be space-separated run ids (got '${EXPECTED_RUN_IDS}')." >&2
  exit 1
fi
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
     < "$WORK/signatures.json" > /dev/null; then
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

# One DSSE envelope per line; the in-toto statement is its base64 payload.
: > "$WORK/statements.jsonl"
while IFS= read -r payload; do
  [ -n "$payload" ] || continue
  printf '%s' "$payload" | base64 -d >> "$WORK/statements.jsonl"
  echo >> "$WORK/statements.jsonl"
done < <(jq -r '.payload // empty' < "$WORK/attestations.jsonl")

# The builder.id of a run of this repository: .../actions/runs/<id>/attempts/<n>.
RUNS_PREFIX="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/"
if [ -n "$EXPECTED_RUN_IDS" ]; then
  PREFIXES="$(for id in $EXPECTED_RUN_IDS; do printf '%s%s/\n' "$RUNS_PREFIX" "$id"; done | jq -R . | jq -s -c .)"
else
  PREFIXES="$(printf '%s\n' "$RUNS_PREFIX" | jq -R . | jq -s -c .)"
fi
VERDICT="$(jq -s -r --arg d "$DIGEST_HEX" --argjson prefixes "$PREFIXES" '
  map(select(.predicateType == "https://slsa.dev/provenance/v0.2"))
  | map(select((.subject // []) | map(.digest.sha256) | index($d) != null))
  | map(.predicate.builder.id // "")
  | map(select(. as $b | $prefixes | any(. as $p | $b | startswith($p))))
  | if length > 0 then .[0] else "none" end
' < "$WORK/statements.jsonl")"
if [ "$VERDICT" = "none" ] || [ -z "$VERDICT" ]; then
  echo "::error::No provenance statement names ${DIGEST} as its subject with a builder.id under ${PREFIXES}." >&2
  exit 1
fi
echo "Provenance subject is ${DIGEST}, built by ${VERDICT}"

if [ -n "$EXPECTED_REVISION" ]; then
  docker buildx imagetools inspect "$REF" --format '{{json .Image}}' > "$WORK/image.json"
  REVISION="$(jq -r '
    (if type == "object" and has("config") then .
     else (to_entries | map(select(.key | startswith("linux/"))) | .[0].value) end)
    | .config.Labels["org.opencontainers.image.revision"] // empty
  ' < "$WORK/image.json")"
  if [ "$REVISION" != "$EXPECTED_REVISION" ]; then
    echo "::error::The image's org.opencontainers.image.revision label is '${REVISION}', not the commit ${EXPECTED_REVISION} it was found for." >&2
    exit 1
  fi
  echo "Revision label ${REVISION} matches the commit"
fi
echo "Verified ${REF}: signed and attested by ${IDENTITY}"
