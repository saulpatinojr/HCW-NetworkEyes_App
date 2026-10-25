# shellcheck shell=bash
# Sourced by scripts/ci/find_release_image.sh and 310-release-version.yml. One function:
#
#   registry_digest <reference>
#
# Prints the manifest digest the reference resolves to and returns:
#   0  the reference exists (the digest is printed on stdout)
#   1  the registry says THIS reference does not exist: the error text names the reference itself followed by
#      "not found", "manifest unknown" or "name unknown" ("ERROR: <the reference>: not found")
#   2  anything else (network error, denied, rate limit, malformed reference): the registry's message is printed
#      on stderr and nothing is printed on stdout
#
# Absence is matched against the queried reference on purpose. A bare "not found" or "404" anywhere in the text
# can be a token endpoint answering 404, a rate-limit page or a shell's "command not found"; reading that as "the tag
# is free" would let a caller create, and so overwrite, a tag that exists. Anything that does not name the reference
# stays status 2. The rehearsal in 200-build-images.yml checks the live wording of a missing tag against this rule.
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
  if grep -qiF -e "${ref}: not found" -e "${ref}: manifest unknown" -e "${ref}: name unknown" "$err"; then
    rm -f "$err"
    return 1
  fi
  cat "$err" >&2
  rm -f "$err"
  return 2
}
