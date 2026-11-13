"""Every workflow job that runs Node.js or Python chooses its version (saulpatinojr/HCW-HybridCloudWorks#1707).

A job that runs `node`, `npm`, `npx`, `python3`, `pip`, `uv` or `uvx` without actions/setup-node or actions/setup-python
gets whatever the runner image ships: on ubuntu-26.04 that was Node.js 24 and Python 3.14 in November 2026, both below
the program's floors (Node.js 26, Python 3.15). Nothing else notices, because a job that names no version has nothing to
read. This is a port of the website's check (scripts/workflow-runtime-setup.test.mjs in HCW-HybridCloudWorks). `uv` and
`uvx` count as Python, because uv runs the interpreter it finds, the runner's own unless one was set up; so
astral-sh/setup-uv counts as setting Python up only when it is given a `python-version` at or above the floor.

A command counts when it is in command position on a line of a `run:` step: at the start, after `$(`, `<(`, a backtick,
`(`, `{`, `|`, `&` or `;`, after a `case` pattern at the start of a line (`check)`), after leading `NAME=value`
assignments (the value plain text, a quoted string, or both run together), or after a word that runs the next one
(`env`, `sudo`, `xargs`, `exec`, `time`, `nice`, `!`, `if`, `then`, `do` and the like) and that word's options (`sudo -u
nobody`, `env -i`). It counts with a path in front too (`/usr/bin/python3`, `./venv/bin/python`), because a path to the
runner's interpreter is still the runner's, and `python3.15.2` counts like `python3`. It does not count in a comment, a
heredoc's body, a quoted string (unless a double-quoted string runs a command with `$(`, `<(` or a backtick; a
single-quoted one may run over several lines, as a `docker run image bash -c '...'` script does) or as an argument
(`docker run image python ...`, or the first word of a line that continues the one before it). The set-up step must come
before the first such step. Limits, on purpose: a job that runs in a `container:` uses that image's runtime and is not
checked; and a script a step calls (`bash scripts/ci/x.sh`) is not read, so a step whose script starts a runtime is
listed in INDIRECT_RUNTIME (as the website's and HCW-CloudAssessor_App's copies do).

A set-up step with its own `if:` may be skipped while a later command still runs on the runner's own interpreter
(Copilot on HCW-NetworkEyes_AddOn#100), so it covers a later step only when that step's `if:` is the same condition,
or is one of the terms the set-up's condition joins with a top-level `||` (whenever that step runs, so did the
set-up). Conditions are compared without a surrounding `${{ }}`, with runs of spaces made one, and a term without
one pair of parentheses around the whole of it. A set-up step with no `if:` covers every later step whose condition
does not test the job's status. A job's own `if:` does not matter here, because it decides whether every step of the
job runs, alike.

The job's status is compared on its own. Without `always()`, `failure()`, `cancelled()` or `success()` in it, a step's
condition includes an unwritten `success()`, so a set-up step with no `if:` is skipped once an earlier step has
failed, while a later `if: always()`, `failure()` or `!cancelled()` step still runs (Copilot on
HCW-MigrateOrchestrator_AddOn#72). So after each job status (success, a failure, a cancel) a later step may run after,
its set-up step must surely run, or depend on the same thing by the rule above, applied to the conditions with their
status-only `&&` terms taken out. `||`, `&&`, `!` and parentheses are followed: `always() && !cancelled()` runs after
success and failure, not after a cancel.

Each set-up step must also ask for the floor or newer (Copilot on HCW-CloudCrawler_App#81): `python-version` or
`python-version-file`, `node-version` or `node-version-file`, read through `${{ env.X }}` (the step's, job's or
workflow's `env:`), `${{ matrix.X }}` (every entry of the job's matrix list) and the named file. A version that names a
line only (`26`, `26.x`, `3.15`) stands for that line's newest release, so it passes when the line is at or above the
floor's; an exact version (`26.10.0`) must be at or above the floor itself; anything else (`26.11.0-rc.1`,
`26.11.0.0`, `lts/*`) cannot be compared. A value this test cannot work out fails it, naming
the step, rather than passing unchecked. A set-up step kept below the floor on purpose is listed, with its reason, in
BELOW_FLOOR_ALLOWED.

Ported from tests/security/test_workflow_runtime_setup.py in HCW-NetworkEyes_AddOn, itself a port of the website's
scripts/workflow-runtime-setup.test.mjs. The checking logic is kept the same so the copies stay in step; only the lists
below, which name this repository's workflows, are its own.

The workflows are read with a small line reader rather than a YAML library, because none is a dependency here. It
relies on the layout every workflow in this repository has (a `jobs:` key at the top level, a `steps:` list, block
`run: |` scripts, `with:` and `env:` written `{ ... }` or as indented `key: value` lines); a file it cannot read that
way fails the test rather than being skipped.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

import pytest

# Computed from this file's place, not imported from conftest, so the file is the same in every repository that has it.
ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"

# Steps that use the runner's own interpreter on purpose, each with its reason, keyed by
# "file > job > step name > runtime". Keyed by step, not job, so a new step in the same job is still checked. A new
# entry needs a reason a reviewer can check, and a comment above the step in the workflow saying the same.
RUNNER_DEFAULT_ALLOWED: dict[str, str] = {
    "200-build-images.yml > build-web > npm audit — check for known vulnerabilities > node": (
        "npm audit only reads package-lock.json against the advisory database, which does not depend on the Node.js "
        "version, and the job holds an OIDC token (id-token: write) to push and sign images, so it installs nothing, "
        "not even an interpreter (the comment above the job's Set up Docker Buildx step says so)"
    ),
    "200-build-images.yml > tag-images > Verify, tag and record every scanned digest > python": (
        "scripts/ci/paths_touch_build.py is standard library only (re, sys, pathlib), and the job holds an OIDC token "
        "(id-token: write) to push tags and sign with cosign, so it installs nothing, not even an interpreter (the "
        "comment above the job's Set up Docker Buildx step says so)"
    ),
    "390-repository-admin.yml > admin > Add the tickets to the board and fill in Product, Priority, Severity and "
    "Workstream from their labels > python": (
        "the board-fill script is standard library only (json, os, sys, urllib), and the job holds the App private "
        "key and PROJECT_TOKEN, so it installs nothing, not even an interpreter (the comment above the job's steps "
        "says so)"
    ),
}

# Steps that start a runtime through a script they run, which the command check cannot see in the `run:` text. Each
# counts as running that runtime, so its set-up step must come first. Same keys, each with a reason.
INDIRECT_RUNTIME: dict[str, str] = {
    "310-release-version.yml > verify > Find the scanned image built from this commit > python": (
        "`bash scripts/ci/find_release_image.sh` runs `python3 scripts/ci/paths_touch_build.py`"
    ),
}

# Set-up steps that ask for a version below the floor on purpose, keyed by the problem `floor_problems` reports, each
# with its reason. A new entry needs a reason a reviewer can check and a record of when it goes away.
BELOW_FLOOR_ALLOWED: dict[str, str] = {
    "300-test-codebase.yml > test > step 2 > python: asks for 3.14, below the floor": (
        "the unit tests still run on Python 3.14 as well as 3.15 while requires-python is >=3.14; TODO.md T-743 "
        "item 4 drops the 3.14 leg, raises requires-python and ruff's target to 3.15 and removes this entry, in one "
        "pull request (the comment above the job says so)"
    ),
}

# Where a command may start: the line's start or an opening or joining character, then any `NAME=value` assignments
# (the value plain text, a quoted string, or both run together: `FOO="a b"`) and words that run the next word
# (`env FOO=1 node`, `sudo node`, `if node ...; then`).
ASSIGNMENT = r"""[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\.)*"|'[^']*'|[^\s"'])*\s+"""
# Words that run the next word, each with the options it may take first: the letters of the options that take an
# argument (`sudo -u nobody`, `nice -n 10`), and any other `-x`/`--long` flag. `command` only with `-p`, because
# `command -v node` looks node up and runs nothing.
WRAPPER_OPTIONS = {
    "env": "uCS",
    "sudo": "ugCDhprtU",
    "xargs": "InPLdaEs",
    "exec": "a",
    "time": "of",
    "nice": "n",
}
WRAPPERS = "|".join(
    [
        rf"{word}(?:\s+(?:-[A-Za-z]*[{takes}]\s*[^\s-]\S*|--?\w[\w-]*(?:=\S+)?))*\s+"
        for word, takes in WRAPPER_OPTIONS.items()
    ]
    + [r"command(?:\s+-p)*\s+", r"(?:if|then|else|elif|do|while|until|!)\s+"]
)
# A `case` pattern that ends at the start of a line (`check)`, `a|b)`), after which a command may follow.
CASE_PATTERN = r"^[^()\s|]+(?:\|[^()\s|]+)*\)\s*"
START = (
    r"(?:^|[$<]\(\s*|`\s*|[({|;&]\s*|"
    + CASE_PATTERN
    + r")(?:"
    + ASSIGNMENT
    + "|"
    + WRAPPERS
    + r")*"
)
# A runtime may be named with a path in front (`/usr/bin/python3`, `./venv/bin/python`): a path to the runner's own
# interpreter is still the runner's. The path holds no `=`, so an assignment (`NODE=/x/node`) is not a command.
PATH = r"(?:[^\s=]*/)?"
COMMAND = {
    "node": re.compile(START + PATH + r"(?:node|npm|npx)(?=\s|$)"),
    "python": re.compile(START + PATH + r"(?:python(?:3(?:\.\d+){0,2})?|pip3?|uvx?)(?=\s|$)"),
}
SETUP = {
    "node": re.compile(r"^actions/setup-node@"),
    "python": re.compile(r"^actions/setup-python@"),
}
# astral-sh/setup-uv sets Python up only when given a `python-version` (see `sets_up`).
SETUP_UV = re.compile(r"^astral-sh/setup-uv@")

# The lowest versions a set-up step may ask for. The program's floors are kept in scripts/version-floors.json in
# HCW-HybridCloudWorks; change them there first, then here.
PYTHON_FLOOR = (3, 15, 0)
NODE_FLOOR = (26, 11, 0)
FLOORS = {"python": PYTHON_FLOOR, "node": NODE_FLOOR}
# The job statuses a step can run after, and the status functions that name them.
STATUSES = {"success", "failure", "cancelled"}
STATUS_CALL = re.compile(r"(!?)\s*\b(always|failure|cancelled|success)\(\s*\)")
# The set-up step's inputs that name the version, directly or through a file in the repository.
VERSION_INPUTS = {
    "python": ("python-version", "python-version-file"),
    "node": ("node-version", "node-version-file"),
}


def _shell_text(run: str) -> str:
    """The script as the shell reads it, for finding commands: comments and heredoc bodies dropped, a line that ends
    in `\\` joined to the next (so the next line's first word is still an argument), single-quoted text emptied, and
    double-quoted text emptied unless it runs a command (`"$(node x)"`, or the older "`node x`"). An escaped backtick
    (`\\``, as in Markdown written to the step summary) is a plain character. A quoted string may run over several
    lines, as the script of `docker run image bash -c '...'` does; what it runs is the container's, not the runner's."""
    out: list[str] = []
    heredocs: list[str] = []
    i, n = 0, len(run)
    while i < n:
        char = run[i]
        if char == "\\" and i + 1 < n:
            out.append(" " if run[i + 1] == "\n" else "" if run[i + 1] == "`" else run[i : i + 2])
            i += 2
        elif char == "'":
            end = run.find("'", i + 1)
            out.append("''")
            i = n if end == -1 else end + 1
        elif char == '"':
            j, body = i + 1, []
            while j < n and run[j] != '"':
                step = 2 if run[j] == "\\" and j + 1 < n else 1
                body.append("" if run[j : j + 2] == "\\`" else run[j : j + step])
                j += step
            text = "".join(body)
            out.append(f'"{text}"' if re.search(r"[$<]\(|`", text) else '""')
            i = j + 1
        elif char == "#" and (i == 0 or run[i - 1] in " \t\n;"):
            end = run.find("\n", i)
            i = n if end == -1 else end
        elif run.startswith("<<", i) and not run.startswith("<<<", i):
            found = re.match(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1", run[i:])
            if found:
                heredocs.append(found.group(2))
            out.append("<<")
            i += len(found.group(0)) if found else 2
        elif char == "\n" and heredocs:
            out.append("\n")
            i += 1
            for delimiter in heredocs:
                while i < n:
                    end = run.find("\n", i)
                    end = n if end == -1 else end
                    line, i = run[i:end], end + 1
                    if line.strip() == delimiter:
                        break
            heredocs = []
        else:
            out.append(char)
            i += 1
    return "".join(out)


def runs_runtime(run: str | None, kind: str) -> bool:
    """True when a run script calls the runtime in command position (see `_shell_text` for what is left out)."""
    return any(COMMAND[kind].search(line.strip()) for line in _shell_text(run or "").split("\n"))


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _meaningful(line: str) -> bool:
    return bool(line.strip()) and not line.lstrip().startswith("#")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _flow_mapping(text: str) -> dict[str, str]:
    """A one-line `{ key: value, ... }` mapping, split on the commas outside quotes and `${{ }}`."""
    inner = text[text.index("{") + 1 : text.rindex("}")]
    parts, depth, quote, start = [], 0, "", 0
    for index, char in enumerate(inner):
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(inner[start:index])
            start = index + 1
    parts.append(inner[start:])
    pairs = (part.partition(":") for part in parts if part.strip())
    return {key.strip(): _unquote(value) for key, _, value in pairs}


def _block(lines: list[str], at: int, indent: int) -> list[str]:
    """The lines under the key on line `at` (at `indent` spaces), up to the next line at that indent or less."""
    block = []
    for line in lines[at + 1 :]:
        if _meaningful(line) and _indent(line) <= indent:
            break
        block.append(line)
    return block


def _mapping(lines: list[str], at: int, indent: int) -> dict[str, str]:
    """The mapping under the key on line `at`: a `{ ... }` on the same line, or the `key: value` lines below it."""
    rest = re.sub(r"\s+#.*$", "", lines[at].split(":", 1)[1]).strip()
    if rest.startswith("{"):
        return _flow_mapping(rest)
    block = _block(lines, at, indent)
    inner = min((_indent(line) for line in block if _meaningful(line)), default=indent + 2)
    pairs = (re.match(rf"^ {{{inner}}}([A-Za-z0-9_.-]+):[ \t]*(.*)$", line) for line in block)
    return {m.group(1): _unquote(re.sub(r"\s+#.*$", "", m.group(2))) for m in pairs if m}


def _matrix(job: list[str], key_indent: int) -> dict[str, list[str]]:
    """The lists of a job's `strategy: matrix:`, each written `[a, b]` or as `- a` lines; {} when it has none."""
    strategy = [
        i
        for i, line in enumerate(job)
        if re.match(rf"^ {{{key_indent}}}strategy:\s*(?:#.*)?$", line)
    ]
    if not strategy:
        return {}
    block = _block(job, strategy[0], key_indent)
    at = [i for i, line in enumerate(block) if re.match(r"^\s+matrix:\s*(?:#.*)?$", line)]
    if not at:
        return {}
    matrix_lines = _block(block, at[0], _indent(block[at[0]]))
    inner = min((_indent(line) for line in matrix_lines if _meaningful(line)), default=0)
    found: dict[str, list[str]] = {}
    for index, line in enumerate(matrix_lines):
        match = re.match(rf"^ {{{inner}}}([A-Za-z0-9_-]+):[ \t]*(.*)$", line)
        if not match:
            continue
        rest = re.sub(r"\s+#.*$", "", match.group(2)).strip()
        if rest.startswith("["):
            found[match.group(1)] = [_unquote(v) for v in rest.strip("[]").split(",") if v.strip()]
        else:
            items = _block(matrix_lines, index, inner)
            found[match.group(1)] = [
                _unquote(i.strip()[2:]) for i in items if i.strip().startswith("- ")
            ]
    return found


def _step_keys(lines: list[str], key_indent: int) -> dict:
    """Every key of one step, among them `name`, `uses`, `run`, `if`, and `with` and `env` as mappings (its first
    line's `- ` already turned into spaces)."""
    keys: dict = {}
    index = 0
    while index < len(lines):
        match = re.match(rf"^ {{{key_indent}}}([A-Za-z_-]+):[ \t]*(.*)$", lines[index])
        index += 1
        if not match:
            continue
        key, rest = match.group(1), match.group(2)
        if key in ("with", "env"):
            keys[key] = _mapping(lines, index - 1, key_indent)
            index += len(_block(lines, index - 1, key_indent))
        elif re.fullmatch(r"[|>][+-]?\d?\s*(?:#.*)?", rest):
            block = []
            while index < len(lines) and (
                not lines[index].strip() or _indent(lines[index]) > key_indent
            ):
                block.append(lines[index])
                index += 1
            keys[key] = textwrap.dedent("\n".join(block)).strip("\n")
        elif key == "uses":
            keys[key] = rest.split()[0] if rest.split() else ""
        else:
            keys[key] = _unquote(re.sub(r"\s+#.*$", "", rest) if key != "run" else rest)
    return keys


def read_jobs(text: str) -> dict[str, dict]:
    """Every job of a workflow: {name: {"container": bool, "env": {...}, "matrix": {...}, "steps": [{"name", "uses",
    "run", "if", "with", "env"}, ...]}}. A job's `env` holds the workflow's `env:` with the job's own on top."""
    lines = text.replace("\r\n", "\n").split("\n")
    top_env = [i for i, line in enumerate(lines) if re.match(r"^env:\s*(?:#.*)?$|^env:\s*\{", line)]
    workflow_env = _mapping(lines, top_env[0], 0) if top_env else {}
    starts = [i for i, line in enumerate(lines) if re.match(r"^jobs:\s*(?:#.*)?$", line)]
    assert len(starts) == 1, "expected one top-level jobs: key"
    body = []
    for line in lines[starts[0] + 1 :]:
        if _meaningful(line) and _indent(line) == 0:
            break
        body.append(line)
    job_indent = min(_indent(line) for line in body if _meaningful(line))
    heads = [i for i, line in enumerate(body) if _meaningful(line) and _indent(line) == job_indent]
    jobs: dict[str, dict] = {}
    for number, head in enumerate(heads):
        match = re.match(rf"^ {{{job_indent}}}([A-Za-z0-9_-]+):\s*(?:#.*)?$", body[head])
        assert match, f"cannot read the job line {body[head]!r}"
        job = body[head + 1 : heads[number + 1] if number + 1 < len(heads) else len(body)]
        key_indent = min(
            (_indent(line) for line in job if _meaningful(line)), default=job_indent + 2
        )
        container = any(re.match(rf"^ {{{key_indent}}}container:", line) for line in job)
        env_at = [i for i, line in enumerate(job) if re.match(rf"^ {{{key_indent}}}env:", line)]
        env = {**workflow_env, **(_mapping(job, env_at[0], key_indent) if env_at else {})}
        steps_at = [
            i
            for i, line in enumerate(job)
            if re.match(rf"^ {{{key_indent}}}steps:\s*(?:#.*)?$", line)
        ]
        steps: list[dict] = []
        if steps_at:
            rest = job[steps_at[0] + 1 :]
            dashes = [line for line in rest if _meaningful(line)]
            assert dashes and dashes[0].lstrip().startswith("- "), (
                f"job {match.group(1)}: steps: is not a list"
            )
            dash = _indent(dashes[0])
            current: list[str] | None = None
            for line in rest:
                if _meaningful(line) and (
                    _indent(line) < dash
                    or (_indent(line) == dash and not line.lstrip().startswith("- "))
                ):
                    break
                if _meaningful(line) and _indent(line) == dash:
                    if current is not None:
                        steps.append(_step_keys(current, dash + 2))
                    current = [" " * (dash + 2) + line[dash + 2 :]]
                elif current is not None:
                    current.append(line)
            if current is not None:
                steps.append(_step_keys(current, dash + 2))
        jobs[match.group(1)] = {
            "container": container,
            "env": env,
            "matrix": _matrix(job, key_indent),
            "steps": steps,
        }
    return jobs


def _normalized(expression: str) -> str:
    """An `if:` expression without a surrounding `${{ }}` and with runs of spaces made one."""
    text = expression.strip()
    wrapped = re.fullmatch(r"\$\{\{(.*)\}\}", text, re.DOTALL)
    return " ".join((wrapped.group(1) if wrapped else text).split())


def _top_level_terms(expression: str, operator: str = "||", unwrap: bool = True) -> list[str]:
    """The terms an expression joins with `||` (or `&&`) outside parentheses and quotes, each without one pair of
    parentheses around the whole of it (unless `unwrap` is false); a one-item list when there is no such operator."""
    terms, depth, quote, start, index = [], 0, "", 0, 0
    while index < len(expression):
        char = expression[index]
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0 and expression.startswith(operator, index):
            terms.append(expression[start:index])
            start = index + len(operator)
            index += len(operator) - 1
        index += 1
    terms.append(expression[start:])
    return [_without_outer_parentheses(term.strip()) if unwrap else term.strip() for term in terms]


def _without_outer_parentheses(term: str) -> str:
    """The term without one pair of parentheses, when that pair encloses the whole of it."""
    if not (term.startswith("(") and term.endswith(")")):
        return term
    depth = 0
    for index, char in enumerate(term):
        depth += {"(": 1, ")": -1}.get(char, 0)
        if depth == 0 and index < len(term) - 1:
            return term
    return term[1:-1].strip()


def condition(step: dict) -> str:
    """A step's `if:` as one comparable expression ("" when it has none)."""
    return _normalized(str(step.get("if") or ""))


def _status_value(expression: str, status: str) -> bool | None:
    """Whether a condition holds after the job so far ended in `status` (success, failure or cancelled): True, False,
    or None when it also depends on something else (`steps.x.outputs.y == 'true'`). `||`, `&&`, `!` and parentheses
    are followed, so `always() && !cancelled()` holds after success and failure only; anything that is not a status
    function or `true`/`false` is unknown."""
    text = expression.strip()
    while (unwrapped := _without_outer_parentheses(text)) != text:
        text = unwrapped
    for operator, decides in (("||", True), ("&&", False)):
        terms = _top_level_terms(text, operator, unwrap=False)
        if len(terms) > 1:
            values = [_status_value(term, status) for term in terms]
            return decides if decides in values else None if None in values else not decides
    if text.startswith("!") and not text.startswith("!="):
        value = _status_value(text[1:], status)
        return None if value is None else not value
    call = re.fullmatch(r"(always|failure|cancelled|success)\(\s*\)", text)
    if call:
        return call.group(1) in ("always", status)
    return {"true": True, "false": False}.get(text)


def _runs_after(expression: str, status: str) -> bool | None:
    """`_status_value` of a step's whole condition, with GitHub's unwritten `success() &&` in front of one that names
    no status function (and of no condition at all)."""
    if not STATUS_CALL.search(expression) and status != "success":
        return False
    return _status_value(expression, status) if expression else True


def statuses(expression: str) -> set[str]:
    """The job statuses a step with this condition may run after (`success` alone for no status function)."""
    return {status for status in STATUSES if _runs_after(expression, status) is not False}


def _without_status(expression: str) -> str:
    """The condition without its top-level `&&` terms that test only the job's status (`always()`, `!cancelled()`)."""
    terms = _top_level_terms(expression, "&&", unwrap=False)
    kept = [term for term in terms if re.sub(r"[\s!()&|]", "", STATUS_CALL.sub("", term))]
    return expression if len(kept) == len(terms) else " && ".join(kept)


def _conditions_cover(given: str, wanted: str) -> bool:
    """True when a set-up step with condition `given` runs whenever a later step with condition `wanted` does: after
    every job status the later step may run after, the set-up step surely runs, or its condition depends on the same
    thing (status terms aside: the same condition, or one of the terms it joins with a top-level `||`)."""
    for status in sorted(STATUSES):
        if _runs_after(wanted, status) is False:
            continue
        runs = _runs_after(given, status)
        if runs is False:
            return False
        if runs is None:
            rest, need = _without_status(given), _without_status(wanted)
            if not (rest in ("", need) or need in _top_level_terms(rest, "||")):
                return False
    return True


def covers(setup: dict, step: dict) -> bool:
    """True when a set-up step runs whenever the later step does: it runs after every job status the later step can
    run after, and, status terms aside, it has no `if:`, the same `if:`, or an `if:` whose top-level `||` terms
    include the later step's."""
    return _conditions_cover(condition(setup), condition(step))


def step_key(file: str, job: str, step: dict, i: int, kind: str) -> str:
    return f"{file} > {job} > {step.get('name') or f'step {i + 1}'} > {kind}"


def unset_steps(
    file: str, jobs: dict[str, dict], indirect: dict[str, str] | None = None
) -> list[str]:
    """The steps of one workflow that run a runtime before (or without) setting it up: "file > job > step > kind". A
    step needs an earlier set-up step that covers it (see `covers`). A step named in `indirect` counts as running its
    runtime even when its `run:` text does not show it."""
    indirect = INDIRECT_RUNTIME if indirect is None else indirect
    found = []
    for name, job in jobs.items():
        if job["container"]:
            continue
        for kind in COMMAND:
            for i, step in enumerate(job["steps"]):
                key = step_key(file, name, step, i, kind)
                if not (runs_runtime(step.get("run"), kind) or key in indirect):
                    continue
                covered = any(
                    sets_up(earlier, job, kind) and covers(earlier, step)
                    for earlier in job["steps"][:i]
                )
                if not covered:
                    found.append(key)
    return found


def _resolved(value: str, step: dict, job: dict, depth: int = 0) -> list[str] | None:
    """The plain values an input stands for: itself, or what `${{ env.X }}` (the step's, job's or workflow's `env:`) or
    `${{ matrix.X }}` (every entry of the job's matrix list) holds. None when it cannot be worked out here."""
    found = re.fullmatch(r"\$\{\{\s*(env|matrix)\.([A-Za-z0-9_-]+)\s*\}\}", value.strip())
    if not found:
        return None if "${{" in value else [value.strip()]
    source, name = found.groups()
    if source == "env":
        env = {**job.get("env", {}), **step.get("env", {})}
        return _resolved(env[name], step, job, depth + 1) if name in env and depth < 5 else None
    return job.get("matrix", {}).get(name) or None


def is_set_up(step: dict, kind: str) -> bool:
    """True for a step that sets the runtime up: actions/setup-node or actions/setup-python, or, for Python,
    astral-sh/setup-uv given a `python-version`."""
    uses = step.get("uses", "")
    if kind == "python" and SETUP_UV.search(uses):
        return "python-version" in (step.get("with") or {})
    return bool(SETUP[kind].search(uses))


def sets_up(step: dict, job: dict, kind: str, root: Path = ROOT) -> bool:
    """True when the step chooses the runtime for the steps after it. setup-uv counts only with a `python-version` at
    or above the floor (a lower one is also reported by the floor test); without one uv uses the runner's Python."""
    if not is_set_up(step, kind):
        return False
    if not SETUP_UV.search(step.get("uses", "")):
        return True
    versions = requested_versions(step, job, root, kind)
    return bool(versions) and all(_below_floor(version, kind) is False for version in versions)


def requested_versions(step: dict, job: dict, root: Path, kind: str) -> list[str] | None:
    """The versions a set-up step asks for, read through `env`, `matrix` and a version file; None when unreadable."""
    direct, from_file = VERSION_INPUTS[kind]
    given = step.get("with") or {}
    if direct in given:
        return _resolved(str(given[direct]), step, job)
    if from_file not in given:
        return None
    paths = _resolved(str(given[from_file]), step, job) or []
    if len(paths) != 1 or not (root / paths[0]).is_file():
        return None
    lines = (line.strip() for line in (root / paths[0]).read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")] or None


def _below_floor(version: str, kind: str) -> bool | None:
    """True when the version is under the floor, False when at or above it, None when it is not one of the forms this
    test reads: `N`, `N.x` and `N.M` name a line and mean its newest release, so only their numbers are compared with
    the floor's (`26` with 26, `3.15` with 3.15); `N.M.P` is exact and compared in full. Anything else, trailing text
    included (`26.11.0-rc.1`, `26.11.0.0`, `lts/*`), is None, so the floor test names the step."""
    found = re.fullmatch(r"v?(\d+)(?:\.x|\.(\d+)(?:\.(\d+))?)?", version.strip())
    if not found:
        return None
    numbers = tuple(int(number) for number in found.groups() if number is not None)
    return numbers < FLOORS[kind][: len(numbers)]


def floor_problems(file: str, jobs: dict[str, dict], root: Path = ROOT) -> list[str]:
    """Every set-up step that asks for a version below the floor, or one this test cannot read, with the reason."""
    problems = []
    for name, job in jobs.items():
        for i, step in enumerate(job["steps"]):
            for kind in COMMAND:
                if not is_set_up(step, kind):
                    continue
                label = f"{file} > {name} > {step.get('name') or f'step {i + 1}'} > {kind}"
                versions = requested_versions(step, job, root, kind)
                if not versions:
                    problems.append(f"{label}: cannot work out the version it asks for")
                for version in versions or []:
                    below = _below_floor(version, kind)
                    if below is None:
                        problems.append(
                            f"{label}: {version!r} is not a version number this test can compare"
                        )
                    elif below:
                        problems.append(f"{label}: asks for {version}, below the floor")
    return problems


@pytest.mark.parametrize(
    "line",
    [
        'token="$(node scripts/github-app-token.mjs)"',
        "npm ci --no-audit",
        "FOO=1 node x",
        "env FOO=1 node x",
        "sudo node x",
        "xargs node x",
        "diff a <(node x)",
        "(node x)",
        "if node x; then",
        "! node x",
        "time node x",
        "exec node x",
        "cd y && npm ci",
        'echo "`node --version`"',
        "env FOO='bar baz' node x.js",
        "FOO=\"a b\"'c d'e node x.js",
        "/opt/node/bin/node x.js",
        "env -i npm ci",
        "nice -n 10 node x.js",
        "xargs -n 1 node",
        "a|b) node x.js ;;",
    ],
)
def test_node_in_command_position_is_found(line):
    assert runs_runtime(line, "node")


@pytest.mark.parametrize(
    "line",
    [
        "cat x | python3 -I check.py",
        "python3.15 -I x.py",
        'compare_out="$(python3 -I scripts/follow_website_base.py --check)"',
        "python -m pip install uv",
        "version=`python3 scripts/check.py`",
        'echo "`python3 --version`"',
        'FOO="bar baz" python3 check.py',
        'STAMP="$(date +%s) run" python3 check.py',
        "uv run python scripts/check.py",
        "uv sync --frozen",
        "uvx zizmor .github",
        "cd y && uv run pytest",
        "/usr/bin/python3 -I check.py",
        "/opt/az/bin/python3 -Im pip check",
        "./venv/bin/python x.py",
        "python3.15.2 -c 'print(1)'",
        "/usr/bin/python3 -c 'print(1)'",
        "env -i python3 check.py",
        "sudo -u nobody python3 check.py",
        "sudo -u runner python3 check.py",
        "time -p python3 check.py",
        "check) python3 scripts/check.py ;;",
        "docker run --rm img bash -c 'x' && python3 y.py",
    ],
)
def test_python_in_command_position_is_found(line):
    assert runs_runtime(line, "python")


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ('echo "run \\`node scripts/x.mjs\\` by hand"', "node"),
        ('docker run --rm img python -c "import azure"', "python"),
        ("# node is not run here", "node"),
        ('for node in items["nodes"]:', "node"),
        ('echo "$NODE_VERSION"', "node"),
        ("nodes=3 nodejs-check", "node"),
        ('echo "the stage is wrong; if pip named the file differently, look"', "python"),
        ("echo 'literal `python3` text'", "python"),
        ("uvicorn app:main", "python"),
        ('FOO="python3 x" true', "python"),
        ("NODE_BIN=/opt/node/bin/node", "node"),
        ("command -v node", "node"),
        ("echo $(foo) python3 x", "python"),
        ("docker run --rm img bash -c '\n  /opt/az/bin/python3 -Im pip check\n'", "python"),
        ("docker run --rm img \\\n  /opt/az/bin/python3 -Im pip check", "python"),
        ("cat > x.txt <<'EOF'\npython3 is named here\nEOF", "python"),
        ("echo x # node y", "node"),
    ],
)
def test_words_that_are_not_commands_are_not_found(line, kind):
    assert not runs_runtime(line, kind)


def test_a_job_that_sets_the_runtime_up_late_or_never_is_flagged():
    text = textwrap.dedent(
        """\
        name: x
        on: push
        jobs:
          late:
            runs-on: ubuntu-26.04
            steps:
              - name: Early
                run: node a.mjs
              - uses: actions/setup-node@abc # v7
          none:
            runs-on: ubuntu-26.04
            steps:
              - run: python3 b.py
          other-setup:
            runs-on: ubuntu-26.04
            steps:
              - uses: astral-sh/setup-uv@abc
              # A comment between steps does not end the list.
              - name: Run
                run: |
                  set -e
                  python3 c.py
          good:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-node@abc
              - run: node a.mjs
          boxed:
            runs-on: ubuntu-26.04
            container: node:26
            steps:
              - run: node a.mjs
        """
    )
    assert unset_steps("x.yml", read_jobs(text)) == [
        "x.yml > late > Early > node",
        "x.yml > none > step 1 > python",
        "x.yml > other-setup > Run > python",
    ]


def test_a_set_up_step_with_its_own_condition_covers_only_steps_it_always_runs_before():
    text = textwrap.dedent(
        """\
        name: x
        on: push
        jobs:
          skipped:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-python@abc
                if: false
              - name: Run
                run: python3 a.py
          same-condition:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-python@abc
                if: ${{ !cancelled() }}
              - name: Run
                if: "!cancelled()"
                run: python3 a.py
          unconditional-setup:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-python@abc
              - name: Run
                if: github.ref == 'refs/heads/main'
                run: python3 a.py
          after-a-failure:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-python@abc
              - name: Run
                if: always()
                run: python3 a.py
          after-a-failure-set-up-too:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-python@abc
                if: always()
              - name: Run
                if: failure()
                run: python3 a.py
          other-condition:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-python@abc
                if: github.event_name == 'push'
              - name: Run
                if: failure()
                run: python3 a.py
          or-term:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-node@abc
                if: matrix.relevant == 'true' || (matrix.name == 'scripts (operations)')
              - name: Run
                if: matrix.name == 'scripts (operations)'
                run: node a.mjs
          and-term:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-node@abc
                if: matrix.relevant == 'true' && matrix.name == 'scripts'
              - name: Run
                if: matrix.name == 'scripts'
                run: node a.mjs
          job-condition:
            if: github.event_name == 'push'
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-node@abc
              - run: node a.mjs
        """
    )
    assert unset_steps("x.yml", read_jobs(text)) == [
        "x.yml > skipped > Run > python",
        "x.yml > after-a-failure > Run > python",
        "x.yml > other-condition > Run > python",
        "x.yml > and-term > Run > node",
    ]


@pytest.mark.parametrize(
    ("setup", "step", "covered"),
    [
        ("${{  a &&   b }}", "a && b", True),
        ("a || b", "b", True),
        ("(a) || (b && c)", "b && c", True),
        ("x == 'p || q' || r", "x == 'p", False),
        ("(a || b) && c", "a", False),
        ("a || b", "a || c", False),
        ("", "anything", True),
        # The job's status: a set-up step with no `if:` runs only after success (the unwritten `success()`).
        ("", "", True),
        ("", "always()", False),
        ("", "${{ !cancelled() }}", False),
        ("", "failure()", False),
        ("${{ !cancelled() }}", "${{ !cancelled() }}", True),
        ("always()", "failure()", True),
        ("always()", "cancelled()", True),
        ("!cancelled()", "always()", False),
        ("!cancelled()", "cancelled()", False),
        ("failure()", "", False),
        ("always() && a", "a", True),
        ("always() && a", "!cancelled() && a", True),
        ("a", "failure() && a", False),
        ("always()", "a || b", True),
        # Status functions joined by `&&` and `||` (Copilot on HCW-CloudAssessor_AddOn#89).
        ("always() && !cancelled()", "cancelled()", False),
        ("always() && !cancelled()", "failure()", True),
        ("failure() || cancelled()", "cancelled()", True),
        ("failure() || cancelled()", "", False),
        ("success() || failure()", "!cancelled()", True),
    ],
)
def test_covers_compares_normalised_conditions_and_top_level_or_terms(setup, step, covered):
    assert covers({"if": setup}, {"if": step}) is covered


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("", {"success"}),
        ("a", {"success"}),
        ("always()", {"success", "failure", "cancelled"}),
        ("!cancelled()", {"success", "failure"}),
        ("always() && !cancelled()", {"success", "failure"}),
        ("failure() || cancelled()", {"failure", "cancelled"}),
        ("(failure() || cancelled()) && a", {"failure", "cancelled"}),
        ("!(failure() || cancelled())", {"success"}),
        ("false", set()),
    ],
)
def test_statuses_follow_and_or_and_not(expression, expected):
    assert statuses(expression) == expected


def test_a_set_up_step_must_ask_for_the_floor_or_newer(tmp_path):
    (tmp_path / ".python-version").write_text(
        "# the line uv and setup-python read\n3.15\n", encoding="utf-8"
    )
    (tmp_path / ".old-version").write_text("3.14\n", encoding="utf-8")
    text = textwrap.dedent(
        """\
        name: x
        on: push
        env:
          PYTHON_VERSION: "3.15"
          OLD: "3.14"
        jobs:
          old:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-python@abc
                with: { python-version: "3.14" }
          new:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-python@abc # v6
                with:
                  python-version: "3.15"
              - uses: actions/setup-python@abc
                with: { python-version-file: .python-version }
              - uses: actions/setup-python@abc
                with: { python-version: "${{ env.PYTHON_VERSION }}" }
              - uses: actions/setup-node@abc
                with: { node-version: 26, package-manager-cache: false }
          old-node:
            runs-on: ubuntu-26.04
            steps:
              - name: Node
                uses: actions/setup-node@abc
                with: { node-version: "24" }
          through-env:
            runs-on: ubuntu-26.04
            env:
              PYTHON_VERSION: ${{ env.OLD }}
            steps:
              - uses: actions/setup-python@abc
                with: { python-version: "${{ env.PYTHON_VERSION }}" }
              - uses: actions/setup-python@abc
                with: { python-version-file: .old-version }
          matrix:
            runs-on: ubuntu-26.04
            strategy:
              matrix:
                python-version: ["3.15", "3.14"]
            steps:
              - uses: actions/setup-python@abc
                with: { python-version: "${{ matrix.python-version }}" }
          unreadable:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-python@abc
              - uses: actions/setup-node@abc
                with: { node-version: "${{ inputs.node }}" }
              - uses: actions/setup-node@abc
                with: { node-version: lts/* }
        """
    )
    assert floor_problems("x.yml", read_jobs(text), tmp_path) == [
        "x.yml > old > step 1 > python: asks for 3.14, below the floor",
        "x.yml > old-node > Node > node: asks for 24, below the floor",
        "x.yml > through-env > step 1 > python: asks for 3.14, below the floor",
        "x.yml > through-env > step 2 > python: asks for 3.14, below the floor",
        "x.yml > matrix > step 1 > python: asks for 3.14, below the floor",
        "x.yml > unreadable > step 1 > python: cannot work out the version it asks for",
        "x.yml > unreadable > step 2 > node: cannot work out the version it asks for",
        "x.yml > unreadable > step 3 > node: 'lts/*' is not a version number this test can compare",
    ]


@pytest.mark.parametrize(
    ("version", "kind", "below"),
    [
        ("26.0.0", "node", True),
        ("26.10.0", "node", True),
        ("26.11.0", "node", False),
        ("26", "node", False),
        ("26.x", "node", False),
        ("v27.0.0", "node", False),
        ("24", "node", True),
        ("3.15", "python", False),
        ("3.15.0", "python", False),
        ("3.14.9", "python", True),
        ("3.14", "python", True),
        ("lts/*", "node", None),
        ("26.11.0-not-a-version", "node", None),
        ("26.11.0garbage", "node", None),
        ("26.11.0-rc.1", "node", None),
        ("26.11.0.0", "node", None),
        ("3.15.0b4", "python", None),
    ],
)
def test_a_line_meets_the_floor_by_its_line_and_an_exact_version_in_full(version, kind, below):
    assert _below_floor(version, kind) is below


def test_setup_uv_sets_python_up_only_with_a_python_version_at_the_floor():
    text = textwrap.dedent(
        """\
        name: x
        on: push
        jobs:
          no-version:
            runs-on: ubuntu-26.04
            steps:
              - uses: astral-sh/setup-uv@abc
              - name: Test
                run: uv run pytest
          new:
            runs-on: ubuntu-26.04
            steps:
              - uses: astral-sh/setup-uv@abc
                with: { python-version: "3.15", enable-cache: false }
              - name: Test
                run: uv run pytest
          old:
            runs-on: ubuntu-26.04
            steps:
              - uses: astral-sh/setup-uv@abc
                with: { python-version: "3.14" }
              - name: Test
                run: uv run pytest
        """
    )
    jobs = read_jobs(text)
    assert unset_steps("x.yml", jobs) == [
        "x.yml > no-version > Test > python",
        "x.yml > old > Test > python",
    ]
    assert floor_problems("x.yml", jobs) == [
        "x.yml > old > step 1 > python: asks for 3.14, below the floor"
    ]


def test_an_indirect_step_counts_as_running_its_runtime():
    jobs = read_jobs(
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - name: Export\n        run: bash x.sh\n"
    )
    key = "x.yml > j > Export > python"
    assert unset_steps("x.yml", jobs, indirect={key: "the script runs uv"}) == [key]
    assert unset_steps("x.yml", jobs, indirect={}) == []


FILES = sorted(p for p in WORKFLOWS.iterdir() if p.suffix in (".yml", ".yaml"))
UNSET = [
    entry for p in FILES for entry in unset_steps(p.name, read_jobs(p.read_text(encoding="utf-8")))
]
FLOOR_PROBLEMS = [
    problem
    for p in FILES
    for problem in floor_problems(p.name, read_jobs(p.read_text(encoding="utf-8")))
]


def test_the_reader_finds_every_job_and_step():
    """A guard against the line reader missing a job: every `runs-on:` line belongs to a job it read, and every job it
    read that has steps has at least one."""
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        jobs = read_jobs(text)
        runners = len(re.findall(r"(?m)^\s+runs-on:", text))
        assert len(jobs) >= runners, (
            f"{path.name}: read {len(jobs)} jobs, the file has {runners} runs-on lines"
        )
        steps = len(re.findall(r"(?m)^\s+steps:\s*$", text))
        assert sum(1 for job in jobs.values() if job["steps"]) == steps, path.name


def test_every_set_up_step_asks_for_the_floor_or_newer():
    assert [problem for problem in FLOOR_PROBLEMS if problem not in BELOW_FLOOR_ALLOWED] == []


def test_every_step_that_runs_node_or_python_comes_after_its_version_is_set_up():
    assert [entry for entry in UNSET if entry not in RUNNER_DEFAULT_ALLOWED] == []


def test_every_allowed_exception_still_exists():
    """So the list cannot hide a step that has since changed, and every entry says why."""
    for entry, reason in RUNNER_DEFAULT_ALLOWED.items():
        assert isinstance(reason, str) and reason.strip(), f"{entry}: an exception needs a reason"
        assert entry in UNSET, entry


def test_every_indirect_step_and_below_floor_exception_still_exists_and_has_a_reason():
    """So a renamed or removed step cannot leave either list pointing at nothing."""
    keys = {
        step_key(p.name, name, step, i, kind)
        for p in FILES
        for name, job in read_jobs(p.read_text(encoding="utf-8")).items()
        for i, step in enumerate(job["steps"])
        for kind in COMMAND
    }
    for entry, reason in INDIRECT_RUNTIME.items():
        assert isinstance(reason, str) and reason.strip(), (
            f"{entry}: an indirect step needs a reason"
        )
        assert entry in keys, entry
    for entry, reason in BELOW_FLOOR_ALLOWED.items():
        assert isinstance(reason, str) and reason.strip(), f"{entry}: an exception needs a reason"
        assert entry in FLOOR_PROBLEMS, (
            f"{entry} is no longer reported; remove it from BELOW_FLOOR_ALLOWED"
        )
