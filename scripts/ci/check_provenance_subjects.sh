#!/usr/bin/env bash
# Called by 320-release-engine.yml before the GitHub Release is created:
#
#   check_provenance_subjects.sh <bundle.intoto.jsonl> <file> [<file> ...]
#
# The provenance file is a list of attestations, one per line (each line is a Sigstore bundle: a signed
# statement, the signing certificate and the transparency-log entry). Each statement names the files it is
# about, as a name and a sha256 fingerprint. This script answers one question without contacting anything:
# does the provenance file name exactly the files given, with the fingerprints those files have right now?
#
#   0  every file given is named with its own sha256, and nothing else is named
#   1  a file is missing from the provenance, has another sha256 there, or the provenance names a file that
#      was not given (the difference is printed on stderr)
#   2  the script was called wrongly, a file is missing, or the provenance file cannot be read as JSON lines
#
# It does NOT check the signature; `gh attestation verify --bundle` does that (the next step of the workflow,
# and the command the README gives a consumer). It exists because a signature check passes for any file the
# provenance names, and the release must carry provenance for all of its files and for nothing else.
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: check_provenance_subjects.sh <bundle.intoto.jsonl> <file> [<file> ...]" >&2
  exit 2
fi

bundle="$1"
shift

if [ ! -s "$bundle" ]; then
  echo "the provenance file ${bundle} is missing or empty" >&2
  exit 2
fi

for file in "$@"; do
  if [ ! -f "$file" ]; then
    echo "${file} is not a file" >&2
    exit 2
  fi
done

# "<sha256>  <name>" for every subject of every statement, sorted, duplicates removed.
if ! attested="$(
  jq -r '
    .dsseEnvelope.payload | @base64d | fromjson
    | select(._type | startswith("https://in-toto.io/Statement/"))
    | .subject[] | "\(.digest.sha256)  \(.name)"
  ' "$bundle" | LC_ALL=C sort -u
)"; then
  echo "the provenance file ${bundle} could not be read as one Sigstore bundle per line" >&2
  exit 2
fi

# The same two columns for the files on disk, by base name (the attestation names a file without its folder).
actual="$(
  for file in "$@"; do
    printf '%s  %s\n' "$(sha256sum "$file" | cut -d' ' -f1)" "$(basename "$file")"
  done | LC_ALL=C sort -u
)"

if [ "$attested" != "$actual" ]; then
  {
    echo "the provenance file does not name exactly the files of this release."
    echo "--- named in ${bundle} (sha256, name):"
    printf '%s\n' "${attested:-(nothing)}"
    echo "--- the files given (sha256, name):"
    printf '%s\n' "$actual"
  } >&2
  exit 1
fi

printf '%s\n' "$actual"
