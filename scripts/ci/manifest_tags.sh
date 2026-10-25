#!/usr/bin/env bash
# Read the build manifest (.deployment-catalog/latest-build.json) on stdin for 370-registry-cleanup.yml.
#
#   scripts/ci/manifest_tags.sh protected <prefix> < .deployment-catalog/latest-build.json
#   scripts/ci/manifest_tags.sh foreign   <prefix> < .deployment-catalog/latest-build.json
#
# <prefix> is `docker.io/<namespace>/<repository>:` (the form 200-build-images.yml writes every `images{}` value
# in). `protected` prints the tag of each `images{}` entry that starts with the prefix, one per line: the tags 370
# must never delete. `foreign` prints how many entries do NOT start with it (for example the entries of the retired
# repository in a manifest that predates the rename): they protect nothing in this repository.
set -euo pipefail

MODE="${1:-}"
PREFIX="${2:-}"
if [ -z "$PREFIX" ] || [[ "$PREFIX" != *: ]]; then
  echo "usage: manifest_tags.sh protected|foreign <prefix>   (the prefix ends in a colon; the manifest is on stdin)" >&2
  exit 2
fi
case "$MODE" in
  protected)
    jq -r --arg prefix "$PREFIX" '.images | to_entries[] | .value | select(startswith($prefix)) | ltrimstr($prefix)'
    ;;
  foreign)
    jq -r --arg prefix "$PREFIX" '[.images | to_entries[] | .value | select(startswith($prefix) | not)] | length'
    ;;
  *)
    echo "usage: manifest_tags.sh protected|foreign <prefix>" >&2
    exit 2
    ;;
esac
