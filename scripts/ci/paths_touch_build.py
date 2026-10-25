#!/usr/bin/env python3
"""Which of these changed files would make 200-build-images.yml build?

    git diff --name-only <built commit> <tagged commit> | python3 scripts/ci/paths_touch_build.py <workflow.yml>

Reads file names (one per line) on stdin and the `on.push.paths` list of the given workflow, prints each file that
matches one of the patterns and exits 1 if there is any (0 and no output when none does). 310-release-version.yml
uses it to accept a tagged commit that changed nothing 200 builds from (documentation, or the manifest commit every
successful 200 ends with) and to refuse one that did.

Only the Python standard library is used: the runner's system Python has no PyYAML, and the `paths:` list is a flat
block of `- pattern` lines. GitHub's glob rules for path filters are followed: `*` matches within one path segment,
`**` matches across segments, `?` matches one character.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def push_paths(workflow_text: str) -> list[str]:
    """The patterns under `on:` / `push:` / `paths:`, in file order."""
    patterns: list[str] = []
    in_on = in_push = in_paths = False
    for raw in workflow_text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        text = raw.strip()
        if indent == 0:
            in_on = text.rstrip(":") in {"on", '"on"', "'on'"} and text.endswith(":")
            in_push = in_paths = False
        elif in_on and indent == 2:
            in_push = text == "push:"
            in_paths = False
        elif in_push and indent == 4:
            in_paths = text == "paths:"
        elif in_paths and indent >= 6 and text.startswith("- "):
            value = re.sub(r"\s+#.*$", "", text[2:].strip())
            patterns.append(value.strip("'\""))
        elif in_paths and indent <= 4:
            in_paths = False
    return patterns


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    out, i = "", 0
    while i < len(pattern):
        char = pattern[i]
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
            continue
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
            continue
        if char == "*":
            out += "[^/]*"
        elif char == "?":
            out += "[^/]"
        else:
            out += re.escape(char)
        i += 1
    return re.compile(out + r"\Z")


def touching(files: list[str], patterns: list[str]) -> list[str]:
    compiled = [glob_to_regex(p) for p in patterns]
    return [f for f in files if any(r.match(f) for r in compiled)]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: paths_touch_build.py <workflow.yml>   (changed file names on stdin)", file=sys.stderr)
        return 2
    patterns = push_paths(Path(argv[1]).read_text(encoding="utf-8"))
    if not patterns:
        print(f"no on.push.paths found in {argv[1]}; refusing to guess what it builds from", file=sys.stderr)
        return 2
    files = [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]
    hits = touching(files, patterns)
    for hit in hits:
        print(hit)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
