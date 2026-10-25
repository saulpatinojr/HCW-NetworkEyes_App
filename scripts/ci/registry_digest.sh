# shellcheck shell=bash
# Sourced by scripts/ci/find_release_image.sh and 310-release-version.yml. One function:
#
#   registry_digest <reference>
#
# Prints the manifest digest the reference resolves to and returns:
#   0  the reference exists (the digest is printed on stdout)
#   1  the registry says it does not exist ("not found", "manifest unknown", HTTP 404)
#   2  anything else (network error, denied, rate limit, malformed reference): the registry's message is printed
#      on stderr and nothing is printed on stdout
#
# The two failures must never be confused. A caller that treats "I could not ask" as "it does not exist" fails
# open: 310-release-version.yml would then go on to create a release tag it could not check was free.
registry_digest() {
  local ref="$1" out err
  err="$(mktemp)"
  if out="$(docker buildx imagetools inspect "$ref" --format '{{.Manifest.Digest}}' 2>"$err")"; then
    rm -f "$err"
    printf '%s\n' "$out"
    return 0
  fi
  if grep -qiE 'not found|manifest unknown|name unknown|\b404\b' "$err"; then
    rm -f "$err"
    return 1
  fi
  cat "$err" >&2
  rm -f "$err"
  return 2
}
