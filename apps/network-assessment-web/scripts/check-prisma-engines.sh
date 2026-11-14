#!/bin/sh
# Checks the Prisma engine files in a node_modules folder against their recorded fingerprints (TODO.md T-744).
#
#   sh scripts/check-prisma-engines.sh <path to prisma-engines.sha256> <path to node_modules>
#
# Run by the deps, builder and migrator-deps stages of the Dockerfile, right after Prisma has downloaded or copied its
# engines. It fails (exit 1) when:
#   1. node_modules/@prisma/engines lacks an engine listed in prisma-engines.sha256, or one differs from its
#      fingerprint (sha256sum -c): the download Prisma made is not the file that was reviewed;
#   2. any other Prisma engine file under node_modules (the copies `prisma generate` makes in .prisma/client and in
#      the prisma package) differs from the fingerprint recorded for its name, or has a name the list does not hold
#      (an engine for another platform, which nothing reviewed).
#
# POSIX sh (Debian's dash runs RUN lines) and coreutils only, so it checks without running any code from node_modules.
set -eu

if [ "$#" -ne 2 ]; then
  echo "usage: sh check-prisma-engines.sh <prisma-engines.sha256> <node_modules>" >&2
  exit 2
fi
fingerprints=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
modules=$2
fix="If Prisma was updated on purpose, run \`node scripts/prisma-engine-hashes.mjs --write\` in apps/network-assessment-web and commit prisma-engines.sha256. Otherwise the engine download was not the reviewed file: do not publish this build."

# 1. The engines @prisma/engines downloaded are the recorded ones. Comment lines (#) are skipped by sha256sum.
if ! (cd "$modules/@prisma/engines" && sha256sum --check --strict --quiet "$fingerprints"); then
  echo "check-prisma-engines: node_modules/@prisma/engines does not hold the engines recorded in prisma-engines.sha256. $fix" >&2
  exit 1
fi

# 2. Every Prisma engine file anywhere under node_modules has the fingerprint recorded for its name.
found=$(mktemp)
checklist=$(mktemp)
trap 'rm -f "$found" "$checklist"' EXIT
# Symbolic links are included: sha256sum reads the file a link points to, which is what Prisma would load, and a
# link that points nowhere fails the check.
find "$modules" \( -type f -o -type l \) \( -name 'libquery_engine-*' -o -name 'query_engine-*' -o -name 'query-engine-*' \
  -o -name 'schema-engine-*' -o -name 'migration-engine-*' -o -name 'prisma-fmt-*' \) >"$found"
count=0
while IFS= read -r file; do
  name=${file##*/}
  hash=$(awk -v name="$name" '$1 !~ /^#/ && NF == 2 && $2 == name { print $1 }' "$fingerprints")
  if [ -z "$hash" ]; then
    echo "check-prisma-engines: $file has no fingerprint in prisma-engines.sha256 (an engine nobody reviewed). $fix" >&2
    exit 1
  fi
  printf '%s  %s\n' "$hash" "$file" >>"$checklist"
  count=$((count + 1))
done <"$found"
if ! sha256sum --check --strict --quiet "$checklist"; then
  echo "check-prisma-engines: a copy of a Prisma engine differs from its fingerprint. $fix" >&2
  exit 1
fi
echo "check-prisma-engines: $count Prisma engine file(s) under $modules match prisma-engines.sha256"
