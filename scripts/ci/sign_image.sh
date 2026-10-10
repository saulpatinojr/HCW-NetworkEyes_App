#!/usr/bin/env bash
# Sign one published image digest and attach its SLSA provenance as a cosign
# attestation (TODO.md T-703). Called by 200-build-images.yml once the image has
# passed Docker Scout (and, for web, the smoke test) — always by digest, never
# by tag:
#
#   scripts/ci/sign_image.sh docker.io/<namespace>/cna@sha256:<64>
#
# Keyless: cosign obtains a short-lived certificate from Fulcio for this
# workflow run's OIDC identity (the job needs `id-token: write`) and records the
# signature in the Sigstore transparency log; no key material exists anywhere.
# The appliances verify with their scripts/ci/verify_image_signature.sh against:
#
#   certificate identity   https://github.com/<owner>/<core>/.github/workflows/200-build-images.yml@refs/heads/main
#   OIDC issuer            https://token.actions.githubusercontent.com
#   attestation type       slsaprovenance02 (https://slsa.dev/provenance/v0.2)
#   predicate.builder.id   https://github.com/<owner>/<core>/actions/runs/<run_id>/attempts/<n>
#
# The provenance predicate is BuildKit's own (build-push-action
# `provenance: true`), read back from the attestation manifest buildx attached
# to the pushed index, so the signed statement describes exactly the build that
# produced this digest. build-push-action sets predicate.builder.id to this
# run's URL; that is asserted here so the appliances' builder check can never be
# the first place a missing value is noticed.
set -euo pipefail

REF="${1:-}"
if ! [[ "$REF" =~ ^docker\.io/[a-z0-9][a-z0-9._-]*/cna@sha256:[0-9a-f]{64}$ ]]; then
  echo "::error::sign_image.sh expects a digest reference docker.io/<namespace>/cna@sha256:<64> (got '${REF}')." >&2
  exit 1
fi
for v in GITHUB_SERVER_URL GITHUB_REPOSITORY GITHUB_RUN_ID; do
  if [ -z "${!v:-}" ]; then
    echo "::error::${v} is not set; sign_image.sh runs inside GitHub Actions only." >&2
    exit 1
  fi
done
EXPECTED_BUILDER_PREFIX="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}/"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "Signing ${REF}"
cosign sign --yes "$REF"

# BuildKit stores the provenance as an in-toto statement in an attestation
# manifest next to the image; imagetools unwraps it. A single-platform build
# prints {"SLSA": {...}}; a multi-platform build prints a platform -> {"SLSA": ...}
# map, from which the first platform's predicate is taken.
docker buildx imagetools inspect "$REF" --format '{{json .Provenance}}' > "$WORK/provenance.json"
if ! jq -e '
      if type == "object" and has("SLSA") then .SLSA
      elif type == "object" then (to_entries | map(select(.value | type == "object" and has("SLSA"))) | .[0].value.SLSA)
      else empty end
    ' "$WORK/provenance.json" > "$WORK/predicate.json"; then
  echo "::error::No BuildKit provenance found on ${REF} (is provenance: true set on its build step?)." >&2
  exit 1
fi
BUILDER_ID="$(jq -r '.builder.id // empty' "$WORK/predicate.json")"
if [[ "$BUILDER_ID" != "$EXPECTED_BUILDER_PREFIX"* ]]; then
  echo "::error::Provenance builder.id '${BUILDER_ID}' does not name this run (expected prefix ${EXPECTED_BUILDER_PREFIX}); refusing to attest." >&2
  exit 1
fi

echo "Attesting SLSA provenance (builder ${BUILDER_ID})"
cosign attest --yes --type slsaprovenance02 --predicate "$WORK/predicate.json" "$REF"
echo "Signed and attested ${REF}"
