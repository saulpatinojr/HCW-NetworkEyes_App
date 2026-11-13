"""Every workflow job that runs Node.js or Python chooses its version (saulpatinojr/HCW-HybridCloudWorks#1707).

A job that runs `node`, `npm`, `npx`, `yarn`, `pnpm`, `python3`, `pip`, `pipx`, `pytest`, `uv` or `uvx` without
actions/setup-node or actions/setup-python gets whatever the runner image ships: on ubuntu-26.04 that was Node.js 24
and Python 3.14 in November 2026, both below the program's floors (Node.js 26, Python 3.15). Nothing else notices,
because a job that names no version has nothing to read. `uv` and `uvx` count as Python, because uv runs the
interpreter it finds, the runner's own unless one was set up; so astral-sh/setup-uv counts as setting Python up only
when it is given a `python-version` at or above the floor. `yarn` and `pnpm` are Node.js programs and count as Node.js;
`pytest` and `pipx` are Python programs and count as Python. pipx builds each tool's virtual environment from
`PIPX_DEFAULT_PYTHON` or, when that is unset, from the interpreter pipx itself runs on
(https://github.com/pypa/pipx/blob/main/src/pipx/interpreter.py, `get_default_python`). GitHub's Ubuntu runner images
install pipx with the image's own python3 (`python3 -m pip install pipx`, actions/runner-images#14654), so after
actions/setup-python a `pipx` step still uses the image's Python unless it is given `--python` (actions/setup-python's
`python-path` output) or `PIPX_DEFAULT_PYTHON`. So a step that runs `pipx` in command position must also choose its
interpreter: `--python` among that pipx command's own words (`pipx run --python "$PYTHON_PATH" ...`), or
`PIPX_DEFAULT_PYTHON` set in front of it (`PIPX_DEFAULT_PYTHON=/p pipx ...`) or in the step's, job's or workflow's
`env:` (Copilot on HCW-NetworkEyes_App#393). A step that does not is reported, named; one kept that way on purpose is
listed, with its reason, in PIPX_ALLOWED. An `export PIPX_DEFAULT_PYTHON=...` earlier in the script is not read; use
`env:` instead.

What pipx is given must also be the set-up Python. The runner's own Python named by its path (`--python
/usr/bin/python3`, `/usr/bin/python3.12` or `/bin/python3`, the same as `PIPX_DEFAULT_PYTHON`) chooses nothing. A
`${{ steps.<id>.outputs.* }}` value counts only when `<id>` is an earlier actions/setup-python step of the same job that
is sure to have run first, by the same rules as a set-up step with an `if:` (below); a missing id, a later step, a step
that is not actions/setup-python or one that may be skipped chooses nothing. A bare `python3.15` and a path under
`${{ env.pythonLocation }}` still count. Settings travel the way the shell passes them: `PIPX_DEFAULT_PYTHON=/p bash -c
'pipx run x'` and `env PIPX_DEFAULT_PYTHON=/p env -S 'pipx run x'` give the inner script the setting, and `sudo` drops
every inherited setting (its default `env_reset`) unless it is given `-E` or `--preserve-env` (bare, or with a list
that names the variable), while `sudo PIPX_DEFAULT_PYTHON=/p pipx ...` sets it.

A command counts when it is in command position on a line of a `run:` step: at the start, after `$(`, `<(`, a backtick,
`(`, `{`, `|`, `&` or `;`, after a `case` pattern at the start of a line (`check)`), after leading `NAME=value`
assignments (the value plain text, a quoted string, or both run together), or after a word that runs the next one
(`env`, `sudo`, `xargs`, `exec`, `time`, `nice`, `nohup`, `stdbuf`, `timeout` with its duration, `command -p`, `!`,
`if`, `then`, `do` and the like) and that word's options (`sudo -u nobody`, `env -i`, `stdbuf -oL`, a `--` that ends
them). A wrapper's long option may be shortened as far as it stays unambiguous, as the commands themselves accept
(`timeout --kill=5`, `nice --adj 5`); an ambiguous one is read as taking no value. A long or short option that takes a
value takes the next word even when it starts with `-` (`timeout --kill-after -5`, `nice -n -5`). It counts with a
path in front too (`/usr/bin/python3`, `./venv/bin/python`, `/usr/bin/env node`), because a path to the runner's
interpreter is still the runner's, and `python3.15.2` counts like `python3`. A `$'...'` string is decoded as the shell
decodes it (`\\xHH`, `\\uHHHH`, `\\UHHHHHHHH`, octal `\\NNN`, `\\n` and the like) and read as one word, so
`$'\\x70ython3'` is `python3` while `$'node\\x20x'` is the one word `node x`. A heredoc's body is read only for the
commands the shell runs in it: `$(...)` and backticks in the body of a heredoc whose delimiter is not quoted or escaped
(`<<EOF`, `<<-EOF`), and nothing in the body of `<<'EOF'`, `<<"EOF"` or `<<\\EOF`. It does not count in a comment,
the rest of a heredoc's body, a quoted string (unless a double-quoted string runs a command with `$(`, `<(` or a backtick; a
single-quoted one may run over several lines, as a `docker run image bash -c '...'` script does) or as an argument
(`docker run image python ...`, `command -v node`, `sudo -u node whoami`, or the first word of a line that continues
the one before it). One more quoted string is read: the script of a shell that is itself in command position and
given `-c` (`bash -c 'node x'`, `sh -euo pipefail -c "..."`, `sudo bash -lc '...'`, `bash -c -- '...'`). That script
runs on the runner, so its commands count, while the same words after `docker run image` stay a container's; an
unquoted script is the one word after `-c` (`bash -c node x.js` runs `node`, while `bash -c echo node` does not), and
text written onto the `-c` is read as the script too (`bash -cnode x`, `bash -ec'node x'`), though bash and dash
refuse that form, so reading it only errs towards reporting. A double-quoted `-c` script is read both ways: as the outer shell reads it (its `$(...)` and backticks run first) and as
the inner shell does. The set-up step must come before the first such step. Limits, on purpose: a job that runs in a
`container:` uses that image's runtime and is not checked; a script a step calls (`bash scripts/ci/x.sh`) is not read,
so a step whose script starts a runtime is listed in INDIRECT_RUNTIME (as HCW-CloudAssessor_App's and
HCW-CloudCrawler_App's copies do). A command substitution inside a double-quoted string (`"$(...)"`, or a backtick
pair) runs on the runner, so it is read like any other script, a `-c` script in it included (`echo "$(bash -c 'node
x')"`); one that hands its script to a container (`"$(docker run img bash -c '...')"`) stays unread.

A composite action (`.github/actions/<name>/action.yml`, `runs: using: composite`) is checked like a job of its own,
named `composite`, so its keys read `.github/actions/<name>/action.yml > composite > step name > runtime`. Its steps
run inside the caller's job, but a caller cannot be relied on to have set the runtime up, so the action sets up what it
runs itself. Its findings go into the same lists as a workflow's, and an exception for one goes in the same lists too.

A set-up step with its own `if:` may be skipped while a later command still runs on the runner's own interpreter
(Copilot on HCW-NetworkEyes_AddOn#100), so it covers a later step only when that step's `if:` makes the set-up's true:
the same condition, one of the terms the set-up's condition joins with a top-level `||`, or a condition that joins one
of those with a top-level `&&` and has no top-level `||` of its own (a step under `a && b` runs only when `a` holds, so
a set-up step under `a || c` has run; Copilot on HCW-HybridCloudWorks#1716; but `a && b || d` can run through `d`
alone, so it is not split; Copilot on HCW-NetworkEyes_App#393). Conditions are compared without a surrounding `${{ }}`, with runs of
spaces made one, and a term without one pair of parentheses around the whole of it. Equal text means equal value only
for values that stay fixed during a job (`matrix`, `github`, `inputs`, `needs`, `vars`, `secrets`); a term that reads
anything else (`env.*`, which a step can change through `$GITHUB_ENV`, `steps.*`, `job`, `runner`, `hashFiles()`) is
never matched by its text, so its step is reported (Copilot on HCW-MigrateOrchestrator_AddOn#74). The one exception is
`steps.<id>` of a step that comes before the set-up step: its outputs, outcome and conclusion are fixed once it has
run (the `core-update.yml` jobs' `steps.refs.outputs.changed`). Prefer the fixed values in such conditions. A set-up
step with no `if:` covers every later step whose condition does not test the job's status. A job's own `if:` does
not matter here, because it decides whether every step of the job runs, alike.

The job's status is compared on its own. Without `always()`, `failure()`, `cancelled()` or `success()` in it, a step's
condition includes an unwritten `success()`, so a set-up step with no `if:` is skipped once an earlier step has
failed, while a later `if: always()`, `failure()` or `!cancelled()` step still runs (Copilot on
HCW-MigrateOrchestrator_AddOn#72). So after each job status (success, a failure, a cancel) a later step may run after,
its set-up step must surely run, or depend on the same thing by the rule above, applied to the conditions with their
status-only `&&` terms taken out, but only from a condition with no top-level `||`: `failure() && a || b` is
`(failure() && a) || b`, so taking `failure()` out would change it (Copilot on HCW-MigrateOrchestrator_AddOn#74).
`||`, `&&`, `!` and parentheses are followed: `always() && !cancelled()` runs after
success and failure, not after a cancel.

Each set-up step must also ask for the floor or newer (Copilot on HCW-CloudCrawler_App#81): `python-version` or
`python-version-file`, `node-version` or `node-version-file`, read through `${{ env.X }}` (the step's, job's or
workflow's `env:`), `${{ matrix.X }}` (every entry of the job's matrix list) and the named file. A version that names a
line only (`26`, `26.x`, `3.15`) stands for that line's newest release, so it passes when the line is at or above the
floor's; an exact version (`26.10.0`) must be at or above the floor itself; anything else (`26.11.0-rc.1`,
`26.11.0.0`, `lts/*`) cannot be compared. A value this test cannot work out fails it, naming
the step, rather than passing unchecked. A set-up step kept below the floor on purpose is listed, with its reason, in
BELOW_FLOOR_ALLOWED.

This is the Python copy of the check; its JavaScript twin is the website's scripts/workflow-runtime-setup.test.mjs in
HCW-HybridCloudWorks, and the other HCW Python repositories copy this file. The command reading (`_shell_text`,
`runs_runtime`, the patterns above it) and the condition rules (`covers`) behave the same as the JavaScript twin; only
the lists below, which name this repository's workflows, are this repository's own. Keep the logic the same in each
copy and change it in all of them together.

The workflows are read with a small line reader rather than a YAML library, because none is a dependency here. It
relies on the layout every workflow in this repository has (a `jobs:` key at the top level, a `steps:` list, block
`run: |` scripts, `with:` and `env:` written `{ ... }` or as indented `key: value` lines); a file it cannot read that
way fails the test rather than being skipped. A `steps:` written on one line (`steps: [{run: ...}]`) or a step written
as one (`- {run: ...}`) is such a file: the reader stops with an error rather than read the job as having no steps.
"""

from __future__ import annotations

import re
import textwrap
import time
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

# Steps that run `pipx` without choosing its interpreter (`--python` or PIPX_DEFAULT_PYTHON) on purpose, keyed by
# "file > job > step name > pipx", each with its reason. Empty: every pipx step here chooses one.
PIPX_ALLOWED: dict[str, str] = {}

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
# argument (`sudo -u nobody`, `nice -n 10`, `stdbuf -oL`), any other `-x`/`--long` flag, and the `--` that ends the
# options (`env -- node`). `timeout` also takes its duration (`timeout 60 node`, `timeout -k 5 1m python3`).
# `command` only with `-p` or `--`, because `command -v node` looks node up and runs nothing. `env -S`
# (`--split-string`) is read as a flag, not as one that takes a value, because its value is the command it runs:
# unquoted, the next word is in command position (`env -S node x.js`); quoted, see ENV_SPLIT_SCRIPT. The same table as
# the website's copy.
WRAPPER_OPTIONS = {
    "env": "uC",
    "sudo": "ugCDhprtTUR",
    "xargs": "InPLdaEs",
    "exec": "a",
    "time": "of",
    "nice": "n",
    "nohup": "",
    "stdbuf": "ioe",
    "timeout": "sk",
}
# The long options of those words that take a value (`timeout --kill-after 5 10 node`, `sudo --user nobody node`), the
# long forms of the letters above: the value follows `=` or is the next word, whatever it starts with. Any other
# `--long[=value]` is a flag, so each long option too can be read only one way (Copilot on
# HCW-MigrateOrchestrator_AddOn#74). The same table as the website's copy.
WRAPPER_LONG_OPTIONS = {
    "env": ("unset", "chdir"),
    "sudo": (
        "user",
        "group",
        "close-from",
        "chdir",
        "host",
        "prompt",
        "role",
        "type",
        "other-user",
        "command-timeout",
        "chroot",
    ),
    "xargs": ("max-args", "max-procs", "delimiter", "arg-file", "max-chars", "process-slot-var"),
    "time": ("output", "format"),
    "nice": ("adjustment",),
    "stdbuf": ("input", "output", "error"),
    "timeout": ("signal", "kill-after"),
}
# Their other long options, which take no value or take one only after `=`. getopt_long, which these commands use,
# accepts any start of a long option that names only one of them (`timeout --kill=5`, `nice --adj 5`), so the whole
# list is needed to tell which starts are unambiguous. The same table as the website's copy.
WRAPPER_LONG_FLAGS = {
    "env": (
        "ignore-environment",
        "null",
        "split-string",
        "block-signal",
        "default-signal",
        "ignore-signal",
        "list-signal-handling",
        "debug",
        "help",
        "version",
    ),
    "sudo": (
        "askpass",
        "background",
        "bell",
        "edit",
        "set-home",
        "help",
        "login",
        "remove-timestamp",
        "reset-timestamp",
        "list",
        "non-interactive",
        "preserve-env",
        "preserve-groups",
        "stdin",
        "shell",
        "version",
        "validate",
    ),
    "xargs": (
        "null",
        "eof",
        "replace",
        "max-lines",
        "interactive",
        "no-run-if-empty",
        "show-limits",
        "verbose",
        "exit",
        "open-tty",
        "help",
        "version",
    ),
    "time": ("append", "portability", "verbose", "quiet", "help", "version"),
    "nice": ("help", "version"),
    "nohup": ("help", "version"),
    "stdbuf": ("help", "version"),
    "timeout": ("foreground", "preserve-status", "verbose", "help", "version"),
}


def _long_option(name: str, word: str) -> str | None:
    """The long option of the wrapper `word` that `--name` names: the option itself, or the one option `name` is the
    start of (`kill` for `kill-after`). None when it names none, or more than one, which the command refuses."""
    every = WRAPPER_LONG_OPTIONS.get(word, ()) + WRAPPER_LONG_FLAGS.get(word, ())
    if name in every:
        return name
    found = [option for option in every if name and option.startswith(name)]
    return found[0] if len(found) == 1 else None


def _forms(word: str, names: tuple[str, ...]) -> list[str]:
    """Every way of writing the long options `names` of the wrapper `word`: each option and each unambiguous start of
    it, longest first."""
    forms = {
        name[:k]
        for name in names
        for k in range(1, len(name) + 1)
        if _long_option(name[:k], word) == name
    }
    return sorted(forms, key=lambda form: (-len(form), form))


def _long_options_of(word: str) -> str:
    """The wrapper's `--long` options: one that takes a value, written in full or shortened (see `_forms`), with its
    value (`--signal=KILL`, `--sig KILL`, `--kill-after -5`), or any other `--long[=value]` as a flag."""
    forms = _forms(word, WRAPPER_LONG_OPTIONS.get(word, ()))
    if not forms:
        return r"--\w[\w-]*(?:=\S+)?"
    joined = "|".join(forms)
    return rf"--(?:{joined})(?:=\S*|\s+\S+)|--(?!(?:{joined})(?![\w-]))\w[\w-]*(?:=\S+)?"


def _options_of(takes: str, word: str) -> str:
    """The options a wrapper may take before the word it runs (see WRAPPER_OPTIONS). Each option can be read only
    one way, so a long run of them cannot make the match try every split (`stdbuf -oL -oL ...` once took seconds): an
    option that takes an argument is the letters up to the first one in `takes`, then its value, joined to it (`-oL`)
    or as the next word, whatever it starts with (`-o L`, `-n -5`); a plain flag has no letter in `takes` (`-i`); then
    the `--long` options (see `_long_options_of`) and the bare `--`."""
    long = _long_options_of(word)
    if not takes:
        return rf"(?:\s+(?:{long}|-\w+|--(?=\s)))*"
    return (
        rf"(?:\s+(?:-(?:(?![{takes}])[A-Za-z])*[{takes}](?:\s+\S+|\S+)"
        rf"|{long}|-(?:(?![{takes}])\w)+|--(?=\s)))*"
    )


# A shell option (`-e`, `-o pipefail`, `-O extglob`, `--rcfile /tmp/rc`, `--login` or the `--` that ends them),
# `letters` being the letters a short option may hold. The options that take an argument (`-o`, `-O`, `--rcfile`,
# `--init-file`) never take one starting with `-`, so an option can be read only one way (otherwise `-o -o -o ...`
# makes the match try every split).
def _shell_option(letters: str) -> str:
    return (
        rf"(?:[-+]{letters}*[oO]\s+[^\s-][\w-]*|--(?:rcfile|init-file)\s+[^\s-]\S*"
        rf"|[-+]{letters}+|--[\w-]+|--(?=\s))"
    )


# A runtime or a wrapper may be named with a path in front (`/usr/bin/python3`, `./venv/bin/python`, `/usr/bin/env`):
# a path to the runner's own interpreter is still the runner's. The path holds no `=`, so an assignment
# (`NODE=/x/node`) is not a command.
PATH = r"(?:[^\s=]*/)?"
# A shell and its options up to the `-c` it is given. The options before it hold no `c`, so the first short option
# that holds one is the `-c` (`-c`, `-lc`, `-ec`), and a long run of options can be read only one way.
SHELL_UP_TO_C = (
    rf"(?:ba|da|k|z)?sh(?:\s+{_shell_option('(?:(?!c)[A-Za-z])')})*\s+-(?:(?!c)[A-Za-z])*c"
)
# What may follow that `c` before the script: more letters and options, then a space.
SHELL_AFTER_C = rf"[A-Za-z]*(?:\s+{_shell_option('[A-Za-z]')})*\s+"
# A shell given `-c`, with its options; the script is the next word, or text written onto the `-c` (`bash -cnode x`).
# bash and dash refuse that second form, so reading it as a script only errs towards reporting.
SHELL_GIVEN_C = rf"{SHELL_UP_TO_C}(?:{SHELL_AFTER_C}|(?=\S))"
# A shell given `-c` is also a word that runs the next one: an unquoted script is that one word (`bash -c node x.js`
# runs `node`, with `x.js` as its `$0`). A quoted script is read by `_shell_text` instead.
SHELL_C = PATH + SHELL_GIVEN_C
WRAPPERS = "|".join(
    [
        rf"{PATH}timeout{_options_of(takes, word)}\s+\d+(?:\.\d+)?[smhd]?\s+"
        if word == "timeout"
        else rf"{'' if word == 'exec' else PATH}{word}{_options_of(takes, word)}\s+"
        for word, takes in WRAPPER_OPTIONS.items()
    ]
    + [
        r"command(?:\s+(?:-p|--(?=\s)))*\s+",
        r"(?:if|then|else|elif|do|while|until|!)\s+",
        SHELL_C,
    ]
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
# yarn and pnpm are Node.js programs; pytest and pipx are Python programs, so they run on the interpreter they were
# installed with, which is the runner's own unless a set-up step came first (pipx also builds each tool's virtual
# environment from that interpreter unless it is given `--python`).
COMMAND = {
    "node": re.compile(START + PATH + r"(?:node|npm|npx|yarn|pnpm)(?=\s|$)"),
    "python": re.compile(
        START + PATH + r"(?:python(?:3(?:\.\d+){0,2})?|pip3?|pipx|pytest|uvx?)(?=\s|$)"
    ),
}
# A shell in command position given a script with `-c` (`bash -c '...'`, `sh -euo pipefail -c "..."`, `sudo bash -lc
# '...'`, `bash -c -- '...'`, `bash -ec'...'`): the script runs on the runner too, so its commands count. The same
# words after `docker run image` are not in command position, so a container's script stays unread.
SHELL_SCRIPT = re.compile(START + PATH + SHELL_UP_TO_C + rf"(?:{SHELL_AFTER_C})?$")
# `env -S` (`--split-string`, or any unambiguous start of it) in command position: env splits its value into words and
# runs them, so a quoted value there is read as a script, like a `-c` shell's (`env -S 'node x.js'`,
# `env --split-string='python3 x.py'`; Copilot on HCW-MigrateOrchestrator_AddOn#74). An unquoted value is the next
# word, which is in command position already.
ENV_SPLIT_SCRIPT = re.compile(
    START
    + PATH
    + "env"
    + _options_of(WRAPPER_OPTIONS["env"], "env")
    + r"\s+(?:-(?:(?![uCS])[A-Za-z])*S|--(?:"
    + "|".join(_forms("env", ("split-string",)))
    + r")=?)\s*$"
)
# `pipx` in command position, with what comes before it (its assignments and wrappers) and its words, up to the end
# of the command (`;`, `&`, `|` or `)`). It has chosen its interpreter when `--python` is one of pipx's own options
# (see `_pipx_option_chooses_python`) or `PIPX_DEFAULT_PYTHON` is one of the assignments in front of it.
PIPX = re.compile(rf"(?P<before>{START}){PATH}pipx(?=\s|$)(?P<words>[^;&|)]*)")
# One word of a command as `_shell_text` leaves it: plain text and quoted strings run together. The first word in
# front of a command may start with what opened it (`(`, `$(`, `&&`, `;`), which is not part of the word.
WORD = re.compile(r"""(?:"(?:[^"\\]|\\.)*"|'[^']*'|[^\s"'])+""")
OPENING = re.compile(r"^(?:[$<]?\(|[`{|;&])+")
# pipx's options that take a value as the next word, so that word is not read as an option or as the app's name.
PIPX_VALUE_OPTIONS = {
    "--spec",
    "--python",
    "--index-url",
    "--pip-args",
    "--suffix",
    "--preinstall",
    "--backend",
    "--fetch-python",
}
# Where `((` opens an arithmetic command rather than two subshells: at the start of a command.
ARITHMETIC_COMMAND = re.compile(r"(?:^|[;&|({]|\b(?:then|else|do|if|elif|while|until|for))\s*$")
# The escapes `$'...'` turns into other characters: these, `\xHH`, `\uHHHH`, `\UHHHHHHHH` and octal `\NNN` (see
# `_ansi_c`); any other `\x` is left as it is.
ANSI_C = {"n": "\n", "t": "\t", "'": "'", '"': '"', "\\": "\\"}
ANSI_C_ESCAPE = re.compile(
    r"\\(x[0-9A-Fa-f]{1,2}|u[0-9A-Fa-f]{1,4}|U[0-9A-Fa-f]{1,8}|[0-7]{1,3}|.)", re.DOTALL
)
# A quoted string that is one plain word once the shell has read it (`$'\x70ython3'` is `python3`), written as that
# word, so it is read in command position like any other.
PLAIN_WORD = re.compile(r"[A-Za-z0-9_./+:@%,-]+")
# The characters a quoted value keeps when `_shell_text` is asked for values (the pipx check); any other becomes `_`, so
# the value stays one word and opens nothing. A `${NAME}` in it is first written `$NAME` (see VARIABLE).
VALUE_UNSAFE = re.compile(r"[^A-Za-z0-9_./:@%+,=$-]")
# A shell variable in a value (`"$PYTHON_PATH"`, `${PYTHON_PATH}`), read from the step's, job's or workflow's `env:`.
VARIABLE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
# A GitHub expression (`${{ steps.py.outputs.python-path }}`), which GitHub replaces before the shell starts. For the
# pipx check it is written as one word, `__gha__` and the expression with every other character made `_`.
GHA_EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)
# The id of each step whose outputs a value reads (`steps.py.outputs.python-path`).
STEP_OUTPUT = re.compile(
    r"(?<![A-Za-z0-9.-])steps\.([A-Za-z0-9_-]+)\.outputs(?![A-Za-z0-9_-])", re.I
)
# The runner's own Python named by its path, which pipx would use instead of the set-up one.
SYSTEM_PYTHON = re.compile(r"(?:/usr)?/bin/python(?:3(?:\.\d+)*)?")
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


def _substitution_close(run: str, at: int) -> int:
    """The index of the `)` that closes the `$(` at `at`, or the end of the text: escapes, quoted strings and the
    substitutions inside them are skipped, so their quotes and parentheses do not count."""
    depth, k, n = 0, at + 1, len(run)
    while k < n:
        char = run[k]
        if char == "\\":
            k += 2
        elif char == "'":
            end = run.find("'", k + 1)
            k = n if end == -1 else end + 1
        elif char == '"':
            k += 1
            while k < n and run[k] != '"':
                if run[k] == "\\":
                    k += 2
                elif run.startswith("$(", k):
                    k = _substitution_close(run, k) + 1
                else:
                    k += 1
            k += 1
        else:
            depth += {"(": 1, ")": -1}.get(char, 0)
            if depth == 0:
                return k
            k += 1
    return n


def _backtick_close(run: str, at: int) -> int:
    """The index of the backtick that closes the one at `at` (an escaped one does not), or the end of the text."""
    k, n = at + 1, len(run)
    while k < n and run[k] != "`":
        k += 2 if run[k] == "\\" else 1
    return min(k, n)


def _ansi_c(body: str) -> str:
    """The text of a `$'...'` string as the shell reads it: `\\n`, `\\t`, `\\'`, `\\"`, `\\\\`, `\\xHH`, `\\uHHHH`,
    `\\UHHHHHHHH` and octal `\\NNN` decoded, cut at a NUL as bash cuts it, and every character that is not printable
    ASCII, a tab or a new line written `_`, which the shell does not split a word on either."""

    def one(match: re.Match[str]) -> str:
        escape = match[1]
        if escape[0] in "xuU" and len(escape) > 1:
            code = int(escape[1:], 16)
            return chr(code) if code <= 0x10FFFF else "_"
        if escape[0] in "01234567":
            return chr(int(escape, 8))
        return ANSI_C.get(escape, match[0])

    text = ANSI_C_ESCAPE.sub(one, body).split("\0", 1)[0]
    return re.sub(r"[^\x20-\x7e\t\n]", "_", text)


def _quoted_text(content: str, mark: str, values: bool) -> str:
    """How `_shell_text` writes a quoted string that runs nothing: `''` (or `""`) when empty, else `'_'` (or `"_"`),
    or, when asked for values, the quotes around the content with every character VALUE_UNSAFE names made `_`."""
    if not content:
        return mark * 2
    if not values:
        return mark + "_" + mark
    return (
        mark + VALUE_UNSAFE.sub("_", VARIABLE.sub(lambda m: "$" + (m[1] or m[2]), content)) + mark
    )


def _heredoc_substitutions(body: str, values: bool) -> list[str]:
    """The commands the shell runs in the body of a heredoc whose delimiter is not quoted (`<<EOF`): each `$(...)` and
    backtick pair, written as `_shell_text` writes them, including those inside `$((...))`. Everything else in the body,
    quotes included, is text; a `\\` makes the next character text."""
    found, k, n = [], 0, len(body)
    while k < n:
        if body[k] == "\\":
            k += 2
        elif body.startswith("$((", k):
            k += 3
        elif body.startswith("$(", k):
            close = _substitution_close(body, k)
            found.append(f"$({_shell_text(body[k + 2 : close], values)})")
            k = close + 1
        elif body[k] == "`":
            close = _backtick_close(body, k)
            found.append(f"`{_shell_text(body[k + 1 : close], values)}`")
            k = close + 1
        else:
            k += 1
    return found


def _shell_text(run: str, values: bool = False) -> str:
    """The script as the shell reads it, for finding commands: comments dropped, a heredoc's body dropped apart from the
    `$(...)` and backticks the shell runs in it when the delimiter is not quoted (see `_heredoc_substitutions`; nothing
    from `<<'EOF'`, `<<"EOF"` or `<<\\EOF`, and not the shift `<<` inside `$((...))` or `((...))`), a line that ends in
    `\\` joined to the next (so the next line's first word is still an argument), single-quoted text and `$'...'` text
    written as `'_'` (`''` when empty; a `$'...'` string that is one plain word once decoded is written as that word,
    see `_ansi_c`), and double-quoted text as `"_"` (`""` when empty) unless it runs a command (`"$(node x)"`, or the
    older "`node x`"). An escaped backtick (`\\``, as in Markdown written to the step summary) is a plain character. A
    quoted string may run over several lines, as the script of `docker run image bash -c '...'` does; what it runs is
    the container's, not the runner's. The one quoted string that is read is the script of a shell in command position
    given `-c` (`bash -c 'node x'`, see SHELL_SCRIPT) or of `env -S`: it is read the same way, on lines of its own, and
    the line after it starts with `:` so that the words after the script (the inner shell's `$0` and arguments) are
    still arguments.

    With `values`, for the pipx check, a quoted string that runs nothing keeps its content (see `_quoted_text`), and a
    script read that way is put between a line holding `\\x01` and the words in front of the shell (its assignments
    and wrappers) and a line holding `\\x02`, so the settings those words make reach the commands inside it."""
    out: list[str] = []
    heredocs: list[tuple[str, bool]] = []
    # Open parentheses inside `$((...))` or `((...))`, where `<<` is a shift; 0 outside.
    arithmetic = 0
    i, n = 0, len(run)

    def line() -> str:
        """The text so far on the current line, read back only to the last new line."""
        tail: list[str] = []
        for part in reversed(out):
            if "\n" in part:
                tail.append(part.rsplit("\n", 1)[1])
                break
            tail.append(part)
        return "".join(reversed(tail))

    def quoted(script: str, text: str) -> None:
        """Add a quoted string as `text`; a `-c` script (or an `env -S` value) also as the inner shell reads it. The
        outer reading stays, because the outer shell runs a `$(...)` or backtick in a double-quoted script before the
        inner shell starts (`bash -c "echo '$(node x)'"`)."""
        head = line().lstrip()
        found = SHELL_SCRIPT.search(head) or ENV_SPLIT_SCRIPT.search(head)
        if not found:
            out.append(text)
        elif values:
            out.append(f"{text}\n\x01{found.group(0)}\n{_shell_text(script, values)}\n\x02\n:")
        else:
            out.append(f"{text}\n{_shell_text(script)}\n:")

    while i < n:
        char = run[i]
        if char == "\\" and i + 1 < n:
            out.append(" " if run[i + 1] == "\n" else "" if run[i + 1] == "`" else run[i : i + 2])
            i += 2
        elif char == "$" and run.startswith("'", i + 1):
            # `$'...'` may hold `\'`, which does not end it.
            j = i + 2
            while j < n and run[j] != "'":
                j += 2 if run[j] == "\\" else 1
            body = _ansi_c(run[i + 2 : j])
            quoted(body, body if PLAIN_WORD.fullmatch(body) else _quoted_text(body, "'", values))
            i = j + 1
        elif char == "'":
            end = run.find("'", i + 1)
            end = n if end == -1 else end
            quoted(run[i + 1 : end], _quoted_text(run[i + 1 : end], "'", values))
            i = end + 1
        elif char == '"':
            # A command substitution in the string (`$(...)`, or a backtick pair) may hold quotes of its own, and it
            # runs on the runner, so its script is read like any other. As text, an escaped backtick prints.
            j, parts = i + 1, []
            while j < n and run[j] != '"':
                if run[j] == "\\":
                    parts.append("" if run[j : j + 2] == "\\`" else run[j : j + 2])
                    j += 2
                elif run.startswith("$(", j) and not run.startswith("$((", j):
                    close = _substitution_close(run, j)
                    parts.append(f"$({_shell_text(run[j + 2 : close], values)})")
                    j = close + 1
                elif run[j] == "`":
                    close = _backtick_close(run, j)
                    parts.append(f"`{_shell_text(run[j + 1 : close], values)}`")
                    j = close + 1
                else:
                    parts.append(run[j])
                    j += 1
            raw, text = run[i + 1 : min(j, n)], "".join(parts)
            # Given to `-c`, the inner shell runs the script, an escaped backtick included.
            script = re.sub(r"\\([\\\"$`\n])", lambda m: "" if m[1] == "\n" else m[1], raw)
            substitutes = re.search(r"[$<]\(|`", text)
            quoted(script, f'"{text}"' if substitutes else _quoted_text(text, '"', values))
            i = j + 1
        elif char == "#" and (i == 0 or run[i - 1] in " \t\n;"):
            end = run.find("\n", i)
            i = n if end == -1 else end
        elif not arithmetic and (
            run.startswith("$((", i)
            or (run.startswith("((", i) and ARITHMETIC_COMMAND.search(line()))
        ):
            opening = "$((" if char == "$" else "(("
            out.append(opening)
            i += len(opening)
            arithmetic = 2
        elif arithmetic and char in "()":
            arithmetic += 1 if char == "(" else -1
            out.append(char)
            i += 1
        elif not arithmetic and run.startswith("<<", i) and not run.startswith("<<<", i):
            found = re.match(r"<<-?\s*(\\?)(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2", run[i:])
            if found:
                # The body is expanded only when no part of the delimiter is quoted or escaped.
                heredocs.append((found.group(3), not (found.group(1) or found.group(2))))
            out.append("<<")
            i += len(found.group(0)) if found else 2
        elif char == "\n" and heredocs:
            out.append("\n")
            i += 1
            for delimiter, expands in heredocs:
                body: list[str] = []
                while i < n:
                    end = run.find("\n", i)
                    end = n if end == -1 else end
                    text, i = run[i:end], end + 1
                    if text.strip() == delimiter:
                        break
                    body.append(text)
                if expands:
                    out.extend(
                        f"{command}\n"
                        for command in _heredoc_substitutions("\n".join(body), values)
                    )
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
        steps_at = [i for i, line in enumerate(job) if re.match(rf"^ {{{key_indent}}}steps:", line)]
        steps: list[dict] = []
        if steps_at:
            # Only a block list is read: `steps: [{run: ...}]` would otherwise read as a job with no steps.
            assert re.fullmatch(r"steps:\s*(?:#.*)?", job[steps_at[0]].strip()), (
                f"job {match.group(1)}: steps: is not a block list"
            )
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
                    # Only a block mapping is read: `- {run: ...}` or `- python3` would read as an empty step.
                    assert re.match(r"[A-Za-z_-]+:(?:\s|$)", line[dash + 2 :]), (
                        f"job {match.group(1)}: a step is not a block mapping: {line.strip()!r}"
                    )
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


def read_action(text: str) -> dict[str, dict]:
    """A composite action's steps (`runs: using: composite`, `runs: steps:`) as one job named `composite`, read by
    `read_jobs` so they are read the same way as a workflow's; {} for any other kind of action (`node24`, `docker`)."""
    lines = text.replace("\r\n", "\n").split("\n")
    runs = [i for i, line in enumerate(lines) if re.match(r"^runs:", line)]
    if not runs:
        return {}
    assert re.fullmatch(r"runs:\s*(?:#.*)?", lines[runs[0]].strip()), "runs: is not a block mapping"
    body = []
    for line in lines[runs[0] + 1 :]:
        if _meaningful(line) and _indent(line) == 0:
            break
        body.append(line)
    inner = min((_indent(line) for line in body if _meaningful(line)), default=2)
    using = rf"^ {{{inner}}}using:\s*['\"]?composite['\"]?\s*(?:#.*)?$"
    if not any(re.match(using, line) for line in body):
        return {}
    wrapped = ["jobs:", "  composite:", *("  " + line if line.strip() else line for line in body)]
    return {"composite": read_jobs("\n".join(wrapped))["composite"]}


def sources(root: Path) -> list[tuple[str, dict[str, dict]]]:
    """Everything this check reads under `root`, each with its jobs: every workflow in .github/workflows, named by its
    file name, then every composite action in .github/actions/<name>/action.yml (or .yaml), named by its path from
    `root`. A repository without .github/actions has none."""
    workflows = sorted(
        p for p in (root / ".github" / "workflows").glob("*") if p.suffix in (".yml", ".yaml")
    )
    actions = sorted(
        p
        for p in (root / ".github" / "actions").glob("*/action.*")
        if p.name in ("action.yml", "action.yaml")
    )
    return [(p.name, read_jobs(p.read_text(encoding="utf-8"))) for p in workflows] + [
        (p.relative_to(root).as_posix(), read_action(p.read_text(encoding="utf-8")))
        for p in actions
    ]


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
    """The condition without its top-level `&&` terms that test only the job's status (`always()`, `!cancelled()`),
    when it has no top-level `||`: `failure() && a || b` is `(failure() && a) || b`, and `a || b` holds when it does
    not (Copilot on HCW-MigrateOrchestrator_AddOn#74)."""
    if len(_top_level_terms(expression, "||")) > 1:
        return expression
    terms = _top_level_terms(expression, "&&", unwrap=False)
    kept = [term for term in terms if re.sub(r"[\s!()&|]", "", STATUS_CALL.sub("", term))]
    return expression if len(kept) == len(terms) else " && ".join(kept)


# A name in a condition whose value is not fixed for the whole job: `env` (a step can write `$GITHUB_ENV`), `steps`,
# `job`, `jobs` and `hashFiles()`. `runner` and `strategy` are fixed for the whole job, like `matrix`. Outside quoted strings and not after a `.`, so
# `needs.build.outputs.env` and `'env.x'` are not one.
CHANGING = re.compile(r"(?<![\w.-])(?:env|steps|job|jobs|hashfiles)(?![\w-])", re.IGNORECASE)


def _fixed_term(term: str, ran: frozenset[str] | set[str] = frozenset()) -> bool:
    """True when a term reads only values fixed from the set-up step on, so equal text means an equal value: no name
    in CHANGING, apart from `steps.<id>` of a step in `ran` (the ids of the steps before the set-up step, whose
    outputs, outcome and conclusion no longer change)."""
    text = re.sub(r"'(?:[^']|'')*'", "''", term)
    text = re.sub(
        r"(?<![\w.-])steps\.([\w-]+)",
        lambda m: "ran" if m[1] in ran else m[0],
        text,
        flags=re.IGNORECASE,
    )
    return not CHANGING.search(text)


def step_ids(steps: list[dict]) -> set[str]:
    """The ids of these steps, for `covers`."""
    return {str(step["id"]) for step in steps if step.get("id") is not None}


def _conditions_cover(
    given: str, wanted: str, ran: frozenset[str] | set[str] = frozenset()
) -> bool:
    """True when a set-up step with condition `given` runs whenever a later step with condition `wanted` does: after
    every job status the later step may run after, the set-up step surely runs, or, status terms aside, the later
    condition is the same, is one of the set-up condition's top-level `||` terms, or, when it has no top-level `||`
    of its own, joins one of them with a top-level `&&` (a step that runs only when `a && b` holds runs only when `a`
    holds, so a set-up step under `a || c` has run; `a && b || d` can run through `d`, so it is not split). The term
    matched must read only values fixed from the set-up step on (`_fixed_term`, with `ran` the ids of the steps before
    it): `env.RUN == 'true'` can be false at the set-up step and true later."""
    for status in sorted(STATUSES):
        if _runs_after(wanted, status) is False:
            continue
        runs = _runs_after(given, status)
        if runs is False:
            return False
        if runs is None:
            rest, need = _without_status(given), _without_status(wanted)
            setup_terms = {
                _without_outer_parentheses(term) for term in [rest, *_top_level_terms(rest, "||")]
            }
            # Split on `&&` only when the later condition has no top-level `||`: `a && c || d` can run through `d`.
            and_terms = (
                _top_level_terms(need, "&&") if len(_top_level_terms(need, "||")) == 1 else []
            )
            step_terms = [_without_outer_parentheses(term) for term in [need, *and_terms]]
            if not (
                rest == ""
                or any(term in setup_terms and _fixed_term(term, ran) for term in step_terms)
            ):
                return False
    return True


def covers(setup: dict, step: dict, ran: frozenset[str] | set[str] = frozenset()) -> bool:
    """True when a set-up step runs whenever the later step does: it runs after every job status the later step can
    run after, and, status terms aside, it has no `if:`, the same `if:`, or an `if:` whose top-level `||` terms
    include the later step's or one of the terms the later step's joins with a top-level `&&`, reading only values
    fixed from the set-up step on (`ran` holds the ids of the steps before it)."""
    return _conditions_cover(condition(setup), condition(step), ran)


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
                    sets_up(earlier, job, kind)
                    and covers(earlier, step, step_ids(job["steps"][:j]))
                    for j, earlier in enumerate(job["steps"][:i])
                )
                if not covered:
                    found.append(key)
    return found


def _gha_tokens(text: str) -> str:
    """The text with each GitHub expression written as one word (see GHA_EXPRESSION)."""
    return GHA_EXPRESSION.sub(
        lambda m: "__gha__" + re.sub(r"[^A-Za-z0-9_.-]", "_", m[1].strip()) + "__", text
    )


def _chooses(
    value: str, setup_ids: frozenset[str] | set[str] = frozenset(), env: dict | None = None
) -> bool:
    """True when a value given to pipx as its Python (`--python`, PIPX_DEFAULT_PYTHON) chooses the set-up one: it is
    not empty (quotes aside), not the runner's own Python named by its path (SYSTEM_PYTHON: `/usr/bin/python3`,
    `/bin/python3`), and every `steps.<id>.outputs` it reads is of a step in `setup_ids`, the earlier
    actions/setup-python steps of the job that are sure to have run first. A shell variable in it is read from `env`
    (the step's, job's and workflow's `env:`) when it is there (`--python "$PYTHON_PATH"` with `PYTHON_PATH: ${{
    steps.python.outputs.python-path }}`); one that is not stays as it is. `python3.15` or a path under
    `${{ env.pythonLocation }}` counts."""
    env = env or {}
    text = value.replace("'", "").replace('"', "")
    text = VARIABLE.sub(
        lambda m: _gha_tokens(str(env[m[1] or m[2]])) if (m[1] or m[2]) in env else m[0], text
    ).strip()
    if not text or SYSTEM_PYTHON.fullmatch(text):
        return False
    return all(found in setup_ids for found in STEP_OUTPUT.findall(text))


def _pipx_option_chooses_python(
    words: str, setup_ids: frozenset[str] | set[str] = frozenset(), env: dict | None = None
) -> bool:
    """True when `--python` (or `--python=...`) is one of pipx's own options among the words after `pipx`, given a
    value that chooses the set-up Python (see `_chooses`; the last one wins, as in pipx). Reading stops at a bare `--`,
    after which every word is the app's, and, for `pipx run`, at the app's name (the first word after `run` that is not
    an option or an option's value), after which every word is the app's argument (`pipx run tool --python x` gives
    `--python` to the tool)."""
    command, value_next, chosen = None, "", False
    for word in words.split():
        if value_next:
            if value_next == "--python":
                chosen = _chooses(word, setup_ids, env)
            value_next = ""
        elif word == "--":
            return chosen
        elif word.startswith("--python="):
            chosen = _chooses(word[len("--python=") :], setup_ids, env)
        elif word in PIPX_VALUE_OPTIONS:
            value_next = word
        elif word.startswith("-"):
            continue
        elif command is None:
            command = word
        elif command == "run":
            return chosen
    return chosen


def _local_default_python(
    before: str, setup_ids: frozenset[str] | set[str] = frozenset(), env: dict | None = None
) -> bool | None:
    """What the words in front of `pipx` do to PIPX_DEFAULT_PYTHON, read in order, the last one that touches it winning
    as in the shell: True when an assignment sets it to a value that chooses the set-up Python (see `_chooses`); False
    when one sets it to anything else, empty included (`PIPX_DEFAULT_PYTHON=`, `PIPX_DEFAULT_PYTHON=''""`), when `env`
    unsets it (`-u`, `--unset`) or clears the whole environment (`-i`, `-`, `--ignore-environment`), or when `sudo`
    resets the environment (it does unless given `-E`, `--preserve-env`, or `--preserve-env=` with a list that names
    the variable); None when none of them touches it, so the inherited value (the step's, job's or workflow's `env:`, or
    the outer command's around a `-c` script) applies (Copilot on HCW-NetworkEyes_App#394). A long option of `env` or
    `sudo` may be shortened as far as it stays unambiguous (see `_long_option`). An assignment after `sudo`'s options
    (`sudo PIPX_DEFAULT_PYTHON=/p pipx`) is sudo's own and sets the variable."""
    chosen: bool | None = None
    wrapper = ""  # "env" or "sudo" while reading that word's options
    following = ""  # the next word is the value of `env -u` ("unset") or of another option ("skip")
    preserve = False  # `sudo` was told to keep PIPX_DEFAULT_PYTHON
    for word in (OPENING.sub("", w) for w in WORD.findall(before)):
        if following:
            if following == "unset" and word == "PIPX_DEFAULT_PYTHON":
                chosen = False
            following = ""
            continue
        if wrapper == "sudo" and (word == "--" or not word.startswith("-")):
            # The end of sudo's options: it resets the environment now, unless told to keep the variable.
            chosen = chosen if preserve else False
            wrapper = ""
            if word == "--":
                continue
        # An assignment word (`NAME=value`): in `FOO=PIPX_DEFAULT_PYTHON=/p` the name is FOO, and the rest its value.
        assignment = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", word, re.DOTALL)
        if assignment:
            if assignment[1] == "PIPX_DEFAULT_PYTHON":
                chosen = _chooses(assignment[2], setup_ids, env)
            wrapper = ""
        elif re.fullmatch(r"(?:\S*/)?env", word):
            wrapper = "env"
        elif re.fullmatch(r"(?:\S*/)?sudo", word):
            wrapper, preserve = "sudo", False
        elif wrapper == "sudo" and word.startswith("--"):
            name, given, value = word[2:].partition("=")
            option = _long_option(name, "sudo")
            if option == "preserve-env":
                preserve = preserve or not given or "PIPX_DEFAULT_PYTHON" in value.split(",")
            elif option in WRAPPER_LONG_OPTIONS["sudo"] and not given:
                following = "skip"
        elif wrapper == "sudo":
            for k in range(1, len(word)):
                if word[k] == "E":
                    preserve = True
                elif word[k] in WRAPPER_OPTIONS["sudo"]:
                    following = "" if word[k + 1 :] else "skip"
                    break
        elif wrapper != "env" or word == "--":
            wrapper = ""
        elif word == "-":
            chosen = False
        elif word.startswith("--"):
            name, given, value = word[2:].partition("=")
            option = _long_option(name, "env")
            if option == "ignore-environment":
                chosen = False
            elif option == "unset" and given:
                chosen = False if value == "PIPX_DEFAULT_PYTHON" else chosen
            elif option in ("unset", "chdir") and not given:
                following = "unset" if option == "unset" else "skip"
        elif word.startswith("-"):
            for k in range(1, len(word)):
                if word[k] == "i":
                    chosen = False
                elif word[k] in "uCS":
                    value = word[k + 1 :]
                    if word[k] != "S" and not value:
                        following = "unset" if word[k] == "u" else "skip"
                    elif word[k] == "u" and value == "PIPX_DEFAULT_PYTHON":
                        chosen = False
                    break
        else:
            wrapper = ""
    if wrapper == "sudo" and not preserve:
        chosen = False
    return chosen


def _or_inherited(local: bool | None, inherited: bool) -> bool:
    """The command's own setting when it has one, else the inherited one."""
    return inherited if local is None else local


def pipx_without_python(
    run: str | None, env: dict, setup_ids: frozenset[str] | set[str] = frozenset()
) -> bool:
    """True when a run script runs `pipx` in command position without choosing its interpreter: no `--python` among
    pipx's own options, and no PIPX_DEFAULT_PYTHON that chooses the set-up Python, read first from the words in front
    of that `pipx` (a whole assignment word, not a value that happens to hold the text, and `env`'s unset and clear
    options and `sudo`'s reset, see `_local_default_python`) and only when they leave it alone from what the command
    inherits: the step's, job's and workflow's `env`, or, inside a `-c` script or an `env -S` value, the setting the
    words in front of that shell make (`PIPX_DEFAULT_PYTHON=/p bash -c 'pipx run x'`). A setting on the command
    overrides the inherited one (Copilot on HCW-NetworkEyes_App#394). A value counts only when it chooses the set-up
    Python (see `_chooses`): `${{ steps.python.outputs.python-path }}` counts when `python` is in `setup_ids`, the ids
    of the earlier actions/setup-python steps that are sure to have run first; passing setup-python's `python-path`
    output that way is the documented way to point pipx at the Python it set up
    (https://github.com/actions/setup-python/blob/main/docs/advanced-usage.md#python-path), as is giving it through a
    variable of the step's `env:` (`--python "$PYTHON_PATH"`), which is read the same way. An inherited value is used
    as written, since GitHub does not expand a variable in `env:`."""
    stack = [_chooses(_gha_tokens(str(env.get("PIPX_DEFAULT_PYTHON") or "")), setup_ids)]
    for line in _shell_text(_gha_tokens(run or ""), values=True).split("\n"):
        line = line.strip()
        if line.startswith("\x01"):
            # A `-c` script (or `env -S` value) starts: it inherits what the words in front of its shell make.
            local = _local_default_python(line[1:], setup_ids, env)
            stack.append(_or_inherited(local, stack[-1]))
            continue
        if line.startswith("\x02"):
            stack = stack[:-1] if len(stack) > 1 else stack
            continue
        for found in PIPX.finditer(line):
            local = _local_default_python(found["before"], setup_ids, env)
            if not (
                _pipx_option_chooses_python(found["words"], setup_ids, env)
                or _or_inherited(local, stack[-1])
            ):
                return True
    return False


def python_setup_ids(steps: list[dict], i: int) -> set[str]:
    """The ids of the actions/setup-python steps before step `i` that are sure to have run before it (see `covers`),
    the only steps whose outputs choose pipx's Python."""
    return {
        str(earlier["id"])
        for j, earlier in enumerate(steps[:i])
        if earlier.get("id") is not None
        and SETUP["python"].search(earlier.get("uses", ""))
        and covers(earlier, steps[i], step_ids(steps[:j]))
    }


def pipx_problems(file: str, jobs: dict[str, dict]) -> list[str]:
    """The steps of one workflow that run `pipx` without choosing its interpreter: "file > job > step > pipx". A job
    in a `container:` is skipped, as `unset_steps` skips it."""
    return [
        step_key(file, name, step, i, "pipx")
        for name, job in jobs.items()
        if not job["container"]
        for i, step in enumerate(job["steps"])
        if pipx_without_python(
            step.get("run"),
            {**job["env"], **(step.get("env") or {})},
            python_setup_ids(job["steps"], i),
        )
    ]


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


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ("env -- node script.mjs", "node"),
        ("command -- node scripts/x.mjs", "node"),
        ("command -p -- npm ci", "node"),
        ("sudo -u nobody -- node x.js", "node"),
        ("sudo -- python3 check.py", "python"),
        ("nohup node x.js &", "node"),
        ("nohup -- python3 x.py", "python"),
        ("stdbuf -oL python3 x.py", "python"),
        ("stdbuf -i0 -o L -eL node x.js", "node"),
        ("timeout 60 node x.js", "node"),
        ("timeout -k 5 1m python3 x.py", "python"),
        ("timeout --signal=KILL 2.5s uv run x.py", "python"),
        ("cd y && timeout 10m npm test", "node"),
        # Long options that take a value, after `=` or as the next word (Copilot on HCW-MigrateOrchestrator_AddOn#74).
        ("timeout --kill-after 5 10 python3 check.py", "python"),
        ("timeout --kill-after=5 10 node x", "node"),
        ("timeout --signal KILL 10 node x", "node"),
        ("timeout -s KILL 10 node x", "node"),
        ("timeout --foreground --signal=TERM 1m python3 x.py", "python"),
        ("sudo --user nobody node x", "node"),
        ("sudo --user=nobody -- python3 x.py", "python"),
        ("env --unset FOO node x", "node"),
        ("env --chdir=/tmp python3 x.py", "python"),
        ("nice --adjustment 5 node x", "node"),
        ("xargs --max-args 1 node", "node"),
        ("xargs --process-slot-var SLOT node x", "node"),
        ("xargs --process-slot-var=SLOT node x", "node"),
        ("stdbuf --output L node x", "node"),
        ("time --output t.txt python3 x.py", "python"),
        # `env -S` runs its value as a command, so a quoted value is read like a `-c` script (Copilot on
        # HCW-MigrateOrchestrator_AddOn#74).
        ("env -S 'node x.js'", "node"),
        ('env -S "python3 x.py"', "python"),
        ("env --split-string='node x'", "node"),
        ("env --split-string 'node x'", "node"),
        ("env -S'node x'", "node"),
        ("env -iS 'python3 x.py'", "python"),
        ("sudo env -S 'FOO=1 node x'", "node"),
        ("env -S node x.js", "node"),
        ("env -S 'pipx run x'", "python"),
    ],
)
def test_wrappers_the_website_copy_reads_are_read(line, kind):
    assert runs_runtime(line, kind)


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ("command -v -- node", "node"),
        ("command -V python3", "python"),
        ("echo nohup node x.js", "node"),
        ("echo timeout 60 python3 x.py", "python"),
        ("timeout-minutes 60 node x.js", "node"),
        ("env -- NODE=1 true", "node"),
        # `-u` takes the next word, so `node` here is the user, not the command.
        ("sudo -u node whoami", "node"),
        ("sudo --user node whoami", "node"),
        ("timeout --signal node 10 x", "node"),
        ("env --unset node x", "node"),
        ("stdbuf --output node x", "node"),
        ("env -S 'echo node'", "node"),
        ("env -S echo node", "node"),
        ("echo env -S 'node x'", "node"),
        ("docker run img env -S 'node x'", "node"),
    ],
)
def test_wrapper_near_misses_are_not_found(line, kind):
    assert not runs_runtime(line, kind)


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ("bash -c 'node x.js'", "node"),
        ('sh -c "python3 x.py"', "python"),
        ("bash -lc 'npm ci'", "node"),
        ("bash -euo pipefail -c 'cd y && python3 x.py'", "python"),
        ("bash --noprofile --norc -eo pipefail -c 'uv sync'", "python"),
        ("/bin/bash -c 'set -e; node x.js'", "node"),
        ("sudo -u nobody bash -c 'python3 x.py'", "python"),
        ("xargs -I{} sh -c 'node {}'", "node"),
        ("bash -c '\n  set -e\n  python3 x.py\n'", "python"),
        ('bash -c "echo \\"$HOME\\" && node x.js"', "node"),
        ("bash -c $'python3 -c \\'print(1)\\''", "python"),
        ("bash -c 'bash -c \"node x.js\"'", "node"),
        ("FOO='a b' bash -c 'node x.js'", "node"),
        # The script's last word is still a command, with nothing after it.
        ("bash -c 'pytest'", "python"),
        # An unquoted script is the one word after `-c` (Copilot on HCW-HybridCloudWorks#1716).
        ("bash -c node x.js", "node"),
        ("sh -c python3 x.py", "python"),
        ("sudo bash -lc -e pytest", "python"),
        ("sh -c 'node'", "node"),
        ('bash -c "cd web && yarn"', "node"),
        ("bash -c 'npm ci && pytest'", "python"),
        ("sudo bash -lc 'pytest'", "python"),
        # Options after `-c`, and options that take a value.
        ("bash -c -e 'node x'", "node"),
        ("bash -c -x 'python3 x'", "python"),
        ("bash -c -- 'node x.js'", "node"),
        ("bash -O extglob -c 'node x'", "node"),
        ("bash +O nullglob -c 'node x'", "node"),
        ("bash --rcfile /tmp/empty -c 'node x'", "node"),
        ("bash --init-file ./rc.sh -eo pipefail -c 'python3 x.py'", "python"),
        ("version=$(sh -c 'node --version')", "node"),
        ("if true; then\n  bash -c 'node x.js'\nfi", "node"),
        # Inside double quotes `\`` is a backtick the inner shell runs; `$'...'` turns `\n` into a new line.
        ('bash -c "echo \\`node --version\\`"', "node"),
        ("bash -c $'echo start\\nnode x.js'", "node"),
        # The outer shell runs `$(...)` and backticks in a double-quoted script first, whatever the inner one makes
        # of them.
        ("bash -c \"echo '$(node x)'\"", "node"),
        ("sh -c \"echo '`node x`' > v\"", "node"),
        ('bash -c "x=1 # $(node y)"', "node"),
        ('bash -c "cat <<EOF\n$(python3 v)\nEOF"', "python"),
        # A substitution inside double quotes runs on the runner, so a `-c` script in it is read (Copilot on
        # HCW-HybridCloudWorks#1716).
        ("echo \"$(bash -c 'node x')\"", "node"),
        ("FOO=\"$(sh -c 'node x')\" true", "node"),
        ('FOO="$(sh -c "node x")" true', "node"),
        ("v=`bash -c 'python3 y'`", "python"),
        ("echo \"`bash -c 'python3 y'`\"", "python"),
        ("x=$(echo \"$(bash -c 'node x')\")", "node"),
    ],
)
def test_a_script_given_to_a_shell_on_the_runner_is_read(line, kind):
    assert runs_runtime(line, kind)


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ("docker run --rm img bash -c 'node x.js'", "node"),
        ('docker run --rm img sh -c "python3 x.py"', "python"),
        ("bash -c 'echo node x.js'", "node"),
        ("bash -c 'echo \"$0\"' node", "node"),
        ('bash -c "echo \\"python3 x.py\\""', "python"),
        ("bash x.sh 'node x.js'", "node"),
        ("ssh -c aes256-ctr host 'node x.js'", "node"),
        ("echo bash -c 'python3 x.py'", "python"),
        ('docker exec web sh -c "python3 x.py"', "python"),
        ("bash -c echo node", "node"),
        ("echo \"$(docker run img bash -c 'node x')\"", "node"),
        ("echo \"$(echo 'node x')\"", "node"),
        ("docker run img bash -c node x.js", "node"),
        ("bash -c 'echo \"$0\"' python3", "python"),
    ],
)
def test_a_script_quoted_for_somewhere_else_is_not_read(line, kind):
    assert not runs_runtime(line, kind)


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ("yarn install --frozen-lockfile", "node"),
        ("pnpm install --frozen-lockfile", "node"),
        ("cd web && pnpm run build", "node"),
        ("/usr/local/bin/yarn test", "node"),
        ("pytest -q", "python"),
        ("cd y && pytest tests/", "python"),
        ("timeout 600 pytest -x", "python"),
        ("pipx run --spec checkov==3.3.30 checkov --directory .", "python"),
        ("pipx install zizmor", "python"),
        ("CI=1 yarn build", "node"),
        ("PYTHONPATH=src pytest tests", "python"),
    ],
)
def test_yarn_pnpm_pytest_and_pipx_are_runtimes(line, kind):
    assert runs_runtime(line, kind)


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ("git diff --exit-code yarn.lock", "node"),
        ("cat pnpm-lock.yaml", "node"),
        ("echo yarn is not used", "node"),
        ("yarnpkg-check x", "node"),
        ("cat pytest.ini", "python"),
        ("mypytest x", "python"),
        ("pytest-check x", "python"),
        ('echo "run pytest by hand"', "python"),
        ("echo pipx", "python"),
        ("./scripts/yarn-audit.sh", "node"),
        ("docker run img pnpm test", "node"),
        ("grep pytest requirements.txt", "python"),
        ("docker run img pytest", "python"),
    ],
)
def test_yarn_pnpm_pytest_and_pipx_as_words_are_not_found(line, kind):
    assert not runs_runtime(line, kind)


@pytest.mark.parametrize(
    ("line", "kind", "found"),
    [
        # `<<` in arithmetic is a shift, not a heredoc that would hide the lines after it.
        ("n=$((1<<k))\npython3 x.py", "python", True),
        ("(( n = n<<k ))\nnode x.js", "node", True),
        ("(( n <<= 1 ))\nnode x.js", "node", True),
        ("echo $(( $(node -p 1) + 1 ))", "node", True),
        ('for ((i = 0; i < 1<<k; i++)); do echo "$i"; done\nnode a.js', "node", True),
        # A heredoc whose delimiter is escaped hides its body, like a quoted one.
        ("cat <<\\EOF\npython3 is named here\nEOF", "python", False),
        ("cat <<-\\EOF > x.txt\n\tnode is named here\n\tEOF", "node", False),
        ("cat <<\\EOF\nnode is named here\nEOF\nnode x.js", "node", True),
        ('cat <<"EOF"\npython3 is named here\nEOF', "python", False),
        # `$'...'` may hold `\'`, which does not end it.
        ("echo $'it\\'s' ; echo '; node x.js'", "node", False),
        ("echo $'it\\'s'\npython3 x.py", "python", True),
        ("printf $'a\\tb\\n'; npm ci", "node", True),
        ("echo $'it\\'s' 'node x'", "node", False),
    ],
)
def test_arithmetic_escaped_heredocs_and_ansi_c_strings_are_read_as_the_shell_does(
    line, kind, found
):
    assert runs_runtime(line, kind) is found


def test_long_runs_of_options_are_read_quickly():
    """Each option can be read only one way, so a long run of them cannot make the match try every split: with two
    readings each, 22 `-oL`s after `stdbuf` took seconds and 16 `-uuu`s after `sudo` more than ten."""
    started = time.perf_counter()
    for line in (
        "stdbuf" + " -oL" * 40 + " -",
        "nice" + " -n10" * 40 + " -",
        "sudo" + " -uuu" * 40 + " -",
        "timeout" + " --signal KILL --kill-after=5" * 40 + " -",
        "sudo" + " --user u --user=u --userx" * 40 + " -",
        "env" + " -S -i -u X" * 40 + " -",
        "env" + " -S 'x'" * 40 + " -",
        "bash " + "-o -o " * 200 + "x'y'",
        "bash " + "-c " * 200 + "x'node y'",
    ):
        assert not runs_runtime(line, "node"), line
    # 200 nested substitutions, quoted and not, each read once per level.
    assert runs_runtime('x="' + '$(echo "' * 200 + "$(bash -c 'node y')" + '")' * 200 + '"', "node")
    assert runs_runtime("$(" * 200 + "node y" + ")" * 200, "node")
    assert time.perf_counter() - started < 1


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
          # A condition on `env` proves nothing; one on a step's outputs does once that step has run before the
          # set-up step (Copilot on HCW-MigrateOrchestrator_AddOn#74).
          env-condition:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-python@abc
                if: env.RUN == 'true'
              - name: Run
                if: env.RUN == 'true'
                run: python3 a.py
          step-ran-first:
            runs-on: ubuntu-26.04
            steps:
              - id: refs
                run: echo x
              - uses: actions/setup-python@abc
                if: steps.refs.outputs.changed == 'true'
              - name: Run
                if: steps.refs.outputs.changed == 'true'
                run: python3 a.py
          step-ran-later:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-python@abc
                if: steps.refs.outputs.changed == 'true'
              - id: refs
                run: echo x
              - name: Run
                if: steps.refs.outputs.changed == 'true'
                run: python3 a.py
        """
    )
    assert unset_steps("x.yml", read_jobs(text)) == [
        "x.yml > skipped > Run > python",
        "x.yml > after-a-failure > Run > python",
        "x.yml > other-condition > Run > python",
        "x.yml > and-term > Run > node",
        "x.yml > env-condition > Run > python",
        "x.yml > step-ran-later > Run > python",
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
        # A later step joined by `&&` with the set-up condition, or with one of its `||` terms, needs it to hold
        # (Copilot on HCW-HybridCloudWorks#1716).
        ("a || b", "a && c", True),
        ("a", "a && c", True),
        ("a || b", "c && (a)", True),
        ("a && b", "a && c", False),
        ("a || b", "c && d", False),
        # The later condition is split on `&&` only when it has no top-level `||` (Copilot on
        # HCW-NetworkEyes_App#393): `a && c || d` can run through `d` alone.
        ("a || b", "a && c || d", False),
        ("a || b", "d || a && c", False),
        ("a || b", "(a && c) || d", False),
        ("a || b", "a && (c || d)", True),
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
        # Status terms come out only of a condition with no top-level `||` (Copilot on
        # HCW-MigrateOrchestrator_AddOn#74): after success with `a` true and `b` false, `failure() && a || b` is false
        # while `a` is true.
        ("failure() && a || b", "a", False),
        ("always() && a || b", "b", True),
        # A term that reads something a step can change is never matched by its text (Copilot on
        # HCW-MigrateOrchestrator_AddOn#74): an earlier step can write `RUN=true` to `$GITHUB_ENV` after the set-up
        # was skipped.
        ("runner.os == 'Linux'", "runner.os == 'Linux'", True),
        ("strategy.job-index == 0", "strategy.job-index == 0", True),
        ("job.status == 'success'", "job.status == 'success'", False),
        ("env.RUN == 'true'", "env.RUN == 'true'", False),
        ("steps.changes.outputs.py == 'true'", "steps.changes.outputs.py == 'true'", False),
        ("github.event_name == 'push' && env.RUN", "github.event_name == 'push' && env.RUN", False),
        ("matrix.os == 'linux' || env.RUN == 'true'", "matrix.os == 'linux'", True),
        ("matrix.os == 'linux'", "matrix.os == 'linux' && env.RUN == 'true'", True),
        ("needs.build.outputs.env == 'x'", "needs.build.outputs.env == 'x'", True),
        ("inputs.mode == 'env.RUN'", "inputs.mode == 'env.RUN'", True),
    ],
)
def test_covers_compares_normalised_conditions_and_top_level_or_terms(setup, step, covered):
    assert covers({"if": setup}, {"if": step}) is covered


@pytest.mark.parametrize(
    ("setup", "step", "ran", "covered"),
    [
        # `steps.<id>` is fixed once that step has run before the set-up step (`ran` is those steps' ids).
        (
            "steps.refs.outputs.changed == 'true'",
            "steps.refs.outputs.changed == 'true'",
            {"refs"},
            True,
        ),
        (
            "steps.refs.outputs.changed == 'true'",
            "steps.refs.outputs.changed == 'true'",
            {"other"},
            False,
        ),
        (
            "steps.refs.outputs.changed == 'true' && env.RUN",
            "steps.refs.outputs.changed == 'true' && env.RUN",
            {"refs"},
            False,
        ),
    ],
)
def test_a_step_that_ran_before_the_set_up_step_has_fixed_outputs(setup, step, ran, covered):
    assert covers({"if": setup}, {"if": step}, ran) is covered


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


@pytest.mark.parametrize(
    ("run", "env", "flagged"),
    [
        ("pipx run --spec checkov==3.3.30 checkov -d .", {}, True),
        ("cd y && pipx install zizmor", {}, True),
        ("bash -c 'pipx run x'", {}, True),
        ('pipx run --python "$P" a && pipx run b', {}, True),
        ("MY_PIPX_DEFAULT_PYTHON=/p pipx run x", {}, True),
        ("pipx run x", {"PIPX_DEFAULT_PYTHON": ""}, True),
        # Only pipx's own options and assignments count (Copilot on HCW-NetworkEyes_App#394): after `--`, and after the
        # app's name for `pipx run`, `--python` is the app's; a value holding the text sets nothing.
        ("pipx run --spec tool -- tool --python", {}, True),
        ("pipx run tool --python x", {}, True),
        ('pipx run --pip-args "--python" tool', {}, True),
        ("env FOO=PIPX_DEFAULT_PYTHON=/p pipx run x", {}, True),
        ('FOO="PIPX_DEFAULT_PYTHON=/p" pipx run x', {}, True),
        ('pipx run --python "$P" tool', {}, False),
        ("pipx run --python=/p tool", {}, False),
        ("pipx run --spec checkov==3.3.30 --python /p checkov -d .", {}, False),
        ("pipx install --python /p tool", {}, False),
        ("pipx install tool --python /p", {}, False),
        ("FOO=1 PIPX_DEFAULT_PYTHON=/p pipx run x", {}, False),
        # An empty value leaves pipx on its own interpreter (Copilot on HCW-NetworkEyes_App#394); a quoted non-empty
        # one still counts, though the shell reading empties it.
        ("PIPX_DEFAULT_PYTHON= pipx run x", {}, True),
        ("PIPX_DEFAULT_PYTHON='' pipx run x", {}, True),
        ('PIPX_DEFAULT_PYTHON="" pipx run x', {}, True),
        ('PIPX_DEFAULT_PYTHON="$P" pipx run x', {}, False),
        ("PIPX_DEFAULT_PYTHON='/opt/py/bin/python3' pipx run x", {}, False),
        ("env PIPX_DEFAULT_PYTHON= pipx run x", {}, True),
        # Empty quotes run together are still empty, a quoted value elsewhere in the script does not vouch for this
        # command's, and the last assignment of the name wins (Copilot on HCW-HybridCloudWorks#1718).
        ("PIPX_DEFAULT_PYTHON=''\"\" pipx run x", {}, True),
        ("PIPX_DEFAULT_PYTHON=\"\"'' pipx run x", {}, True),
        ("PIPX_DEFAULT_PYTHON='' pipx run x; PIPX_DEFAULT_PYTHON=\"$P\" echo", {}, True),
        ("PIPX_DEFAULT_PYTHON='' pipx a; PIPX_DEFAULT_PYTHON='/p' pipx b", {}, True),
        ("PIPX_DEFAULT_PYTHON='/p' PIPX_DEFAULT_PYTHON= pipx run x", {}, True),
        ("PIPX_DEFAULT_PYTHON= PIPX_DEFAULT_PYTHON='/p' pipx run x", {}, False),
        ('PIPX_DEFAULT_PYTHON=""/p pipx run x', {}, False),
        ('pipx run --python "$P" --spec x x', {}, False),
        ("pipx run --python=/opt/py/bin/python3 x", {}, False),
        ("PIPX_DEFAULT_PYTHON=/p pipx run x", {}, False),
        ("env PIPX_DEFAULT_PYTHON=/p pipx run x", {}, False),
        ("pipx run x", {"PIPX_DEFAULT_PYTHON": "/p"}, False),
        # A setting on the command overrides the inherited one (Copilot on HCW-NetworkEyes_App#394): set empty, unset
        # or cleared by `env`, it chooses nothing; `--python` still chooses.
        ("PIPX_DEFAULT_PYTHON= pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, True),
        ("PIPX_DEFAULT_PYTHON='' pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, True),
        ("env -u PIPX_DEFAULT_PYTHON pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, True),
        ("env -uPIPX_DEFAULT_PYTHON pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, True),
        ("env --unset PIPX_DEFAULT_PYTHON pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, True),
        ("env --unset=PIPX_DEFAULT_PYTHON pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, True),
        ("env -i pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, True),
        ("env --ignore-environment pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, True),
        (
            "env --chdir /tmp -u PIPX_DEFAULT_PYTHON pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            True,
        ),
        ("PIPX_DEFAULT_PYTHON=/p env -u PIPX_DEFAULT_PYTHON pipx run x", {}, True),
        ("pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, False),
        (
            "env -u PIPX_DEFAULT_PYTHON pipx run --python /p x",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            False,
        ),
        ("env -i PIPX_DEFAULT_PYTHON=/p pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, False),
        ("env -u OTHER pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, False),
        # `-u` is sudo's user, not env's unset; `-E` keeps the inherited value (sudo resets it otherwise, below).
        ("sudo -E -u PIPX_DEFAULT_PYTHON pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, False),
        ("env -S 'pipx run x'", {}, True),
        ("env -S 'pipx run x'", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, False),
        ("(PIPX_DEFAULT_PYTHON=/p pipx run x)", {}, False),
        ("cd y &&PIPX_DEFAULT_PYTHON=/p pipx run x", {}, False),
        ("(PIPX_DEFAULT_PYTHON= pipx run x)", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, True),
        ("x=$(env -i pipx run x)", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, True),
        ("echo pipx", {}, False),
        ("docker run img pipx run x", {}, False),
        ("python3 -m pip install pipx", {}, False),
    ],
)
def test_a_pipx_command_must_choose_its_python(run, env, flagged):
    assert pipx_without_python(run, env) is flagged


def test_pipx_steps_are_read_with_the_step_job_and_workflow_env():
    text = textwrap.dedent(
        """\
        name: x
        on: push
        env:
          FROM_WORKFLOW: "1"
        jobs:
          bare:
            runs-on: ubuntu-26.04
            steps:
              - name: Scan
                run: pipx run --spec checkov==3.3.30 checkov -d .
          step-env:
            runs-on: ubuntu-26.04
            steps:
              - id: python
                uses: actions/setup-python@abc
                with: { python-version: "3.15" }
              - name: Scan
                env:
                  PIPX_DEFAULT_PYTHON: ${{ steps.python.outputs.python-path }}
                run: pipx run checkov -d .
          job-env:
            runs-on: ubuntu-26.04
            env: { PIPX_DEFAULT_PYTHON: /opt/py/bin/python3 }
            steps:
              - run: pipx run checkov -d .
          option:
            runs-on: ubuntu-26.04
            steps:
              - id: python
                uses: actions/setup-python@abc
                with: { python-version: "3.15" }
              - name: Scan
                env:
                  PYTHON_PATH: ${{ steps.python.outputs.python-path }}
                run: pipx run --python "$PYTHON_PATH" --spec checkov==3.3.30 checkov -d .
          boxed:
            runs-on: ubuntu-26.04
            container: python:3.15
            steps:
              - run: pipx run checkov -d .
        """
    )
    assert pipx_problems("x.yml", read_jobs(text)) == ["x.yml > bare > Scan > pipx"]
    workflow_env = text.replace('FROM_WORKFLOW: "1"', "PIPX_DEFAULT_PYTHON: /opt/py/bin/python3")
    assert pipx_problems("x.yml", read_jobs(workflow_env)) == []


@pytest.mark.parametrize(
    ("line", "kind", "found"),
    [
        # An unquoted heredoc runs the `$(...)` and backticks in its body; a quoted or escaped one runs nothing, and
        # the rest of a body is text, quotes included.
        ("cat <<EOF\n$(python3 check.py)\nEOF", "python", True),
        ("cat <<-EOF\n\tvalue: $(node x.js)\n\tEOF", "node", True),
        ("cat <<EOF > v.txt\n`node --version`\nEOF", "node", True),
        ("cat <<EOF\n$(( $(node -p 1) + 1 ))\nEOF", "node", True),
        ("cat <<EOF\n'$(python3 x.py)'\nEOF", "python", True),
        ("cat <<EOF\n$(bash -c 'node x')\nEOF", "node", True),
        ("cat <<A <<'B'\n$(node x)\nA\n$(python3 y)\nB", "node", True),
        ("cat <<A <<'B'\n$(node x)\nA\n$(python3 y)\nB", "python", False),
        ("cat <<EOF\ntext\nEOF\nnode x.js", "node", True),
        ("cat <<EOF\nnode is named here\nEOF", "node", False),
        ("cat <<'EOF'\n$(node x)\nEOF", "node", False),
        ('cat <<"EOF"\n$(python3 x)\nEOF', "python", False),
        ("cat <<\\EOF\n`node x`\nEOF", "node", False),
        ("cat <<EOF\n\\$(node x)\nEOF", "node", False),
        ("cat <<EOF\n$(echo node)\nEOF", "node", False),
        # Text written onto `-c` is read as the script (bash and dash refuse it, so this only errs towards reporting).
        ("bash -cnode x", "node", True),
        ("sh -cpython3 x.py", "python", True),
        ("bash -c'node x'", "node", True),
        ("bash -ec'python3 x.py'", "python", True),
        ("sudo bash -lc'pytest'", "python", True),
        ("bash -ce 'node x'", "node", True),
        ("docker run img bash -cnode x", "node", False),
        ("bash -c'echo node'", "node", False),
        ("echo bash -cnode", "node", False),
        # `$'...'` is decoded, then read as one word.
        ("$'\\x70ython3' x.py", "python", True),
        ("$'\\160ython3' x.py", "python", True),
        ("$'\\u0070ython3' x.py", "python", True),
        ("$'\\U00000070ython3' x.py", "python", True),
        ("$'/usr/bin/\\x70ython3' x.py", "python", True),
        ("FOO=1 $'n\\157de' x", "node", True),
        ("$'node\\0x' y", "node", True),
        ("bash -c $'node\\x20x'", "node", True),
        ("bash -c $'\\x6eode x'", "node", True),
        ("$'node\\x20x'", "node", False),
        ("echo $'\\x6eode'", "node", False),
        ("$'\\x6eodejs' x", "node", False),
        ("$'\\x' node", "node", False),
        # A wrapper named by its path is the same wrapper.
        ("/usr/bin/env node x.js", "node", True),
        ("/usr/bin/timeout 5 python3 x.py", "python", True),
        ("/usr/bin/sudo -u nobody node x", "node", True),
        ("/usr/bin/nice -n 5 node x", "node", True),
        ("./node_modules/.bin/pnpm install", "node", True),
        ("/usr/bin/env bash -c 'python3 x.py'", "python", True),
        ("/usr/bin/env -S 'node x'", "node", True),
        ("echo /usr/bin/env node", "node", False),
        ("/opt/tools/envy node x", "node", False),
        # A long option may be shortened while it names one option; an ambiguous start takes no value.
        ("timeout --kill=5 10 node x", "node", True),
        ("timeout --kill 5 10 node x", "node", True),
        ("timeout --sig KILL 10 python3 x.py", "python", True),
        ("env --uns FOO node x", "node", True),
        ("nice --adj 5 node x", "node", True),
        ("xargs --max-a 1 node", "node", True),
        ("sudo --us nobody node x", "node", True),
        ("stdbuf --out L node x", "node", True),
        ("sudo --command-t 5 python3 x.py", "python", True),
        ("xargs --max node x", "node", True),
        ("env --split 'node x'", "node", True),
        ("sudo --us node whoami", "node", False),
        ("timeout --sig node 10 x", "node", False),
        ("nice --adj node x", "node", False),
        # An option that takes a value takes the next word whatever it starts with.
        ("timeout --kill-after -5 10 node x", "node", True),
        ("nice -n -5 node x", "node", True),
        ("nice --adjustment -5 python3 x.py", "python", True),
        ("timeout --kill-after -5 node x", "node", False),
        # sudo's other options that take a value.
        ("sudo -T 5 node x", "node", True),
        ("sudo --command-timeout=5 node x", "node", True),
        ("sudo -R /srv node x", "node", True),
        ("sudo -T node whoami", "node", False),
    ],
)
def test_round_two_forms_are_read_as_the_shell_reads_them(line, kind, found):
    assert runs_runtime(line, kind) is found


@pytest.mark.parametrize(
    ("run", "env", "ids", "flagged"),
    [
        # A heredoc's body runs pipx only through a substitution of an unquoted heredoc.
        ("cat <<EOF\n$(pipx run x)\nEOF", {}, [], True),
        ("cat <<'EOF'\n$(pipx run x)\nEOF", {}, [], False),
        # A step's output counts only for an earlier actions/setup-python step that is sure to have run (`ids`).
        ("pipx run --python ${{ steps.py.outputs.python-path }} x", {}, ["py"], False),
        ("pipx run --python ${{ steps.py.outputs.python-path }} x", {}, [], True),
        ("pipx run --python ${{ steps.py.outputs.python-path }} x", {}, ["other"], True),
        ('pipx run --python "${{ steps.py.outputs.python-path }}" x', {}, ["py"], False),
        ("pipx run --python=${{ steps.py.outputs.python-path }} x", {}, [], True),
        ("pipx run --python ${{ steps.py.outputs['python-path'] }} x", {}, ["py"], False),
        (
            "pipx run x",
            {"PIPX_DEFAULT_PYTHON": "${{ steps.py.outputs.python-path }}"},
            ["py"],
            False,
        ),
        ("pipx run x", {"PIPX_DEFAULT_PYTHON": "${{ steps.py.outputs.python-path }}"}, [], True),
        ("PIPX_DEFAULT_PYTHON='${{ steps.py.outputs.python-path }}' pipx run x", {}, [], True),
        ("PIPX_DEFAULT_PYTHON=${{ steps.py.outputs.python-path }} pipx run x", {}, ["py"], False),
        # A variable of the step's `env:` is read the same way; one that is not there stays a value.
        (
            'pipx run --python "$PYTHON_PATH" x',
            {"PYTHON_PATH": "${{ steps.py.outputs.python-path }}"},
            ["py"],
            False,
        ),
        (
            'pipx run --python "$PYTHON_PATH" x',
            {"PYTHON_PATH": "${{ steps.py.outputs.python-path }}"},
            [],
            True,
        ),
        ("pipx run --python ${PYTHON_PATH} x", {"PYTHON_PATH": "/usr/bin/python3"}, [], True),
        ('PIPX_DEFAULT_PYTHON="$P" pipx run x', {"P": "/usr/bin/python3"}, [], True),
        ("pipx run x", {"PIPX_DEFAULT_PYTHON": "$P", "P": "/usr/bin/python3"}, [], False),
        # Settings in front of a `-c` shell or `env -S` reach the script inside it.
        ("PIPX_DEFAULT_PYTHON=/p bash -c 'pipx run y'", {}, [], False),
        ("env PIPX_DEFAULT_PYTHON=/p env -S 'pipx run y'", {}, [], False),
        ("PIPX_DEFAULT_PYTHON=/p bash -c \"bash -c 'pipx run y'\"", {}, [], False),
        ("PIPX_DEFAULT_PYTHON=/p bash -c'pipx run y'", {}, [], False),
        ("echo \"$(PIPX_DEFAULT_PYTHON=/p bash -c 'pipx run y')\"", {}, [], False),
        ("PIPX_DEFAULT_PYTHON= bash -c 'pipx run y'", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        (
            "env -u PIPX_DEFAULT_PYTHON bash -c 'pipx run y'",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            [],
            True,
        ),
        ("env -i bash -c 'pipx run y'", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("PIPX_DEFAULT_PYTHON=/p bash -c 'PIPX_DEFAULT_PYTHON= pipx run y'", {}, [], True),
        ("PIPX_DEFAULT_PYTHON=/p bash -c 'true'; pipx run y", {}, [], True),
        ('PIPX_DEFAULT_PYTHON=/p bash -c "echo $(pipx run y)"', {}, [], True),
        (
            "PIPX_DEFAULT_PYTHON=/usr/bin/python3 bash -c 'pipx run y'",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            [],
            True,
        ),
        # sudo resets the environment unless told to keep the variable; its own assignment sets it.
        ("sudo pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("sudo -E pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], False),
        ("sudo --preserve-env pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], False),
        (
            "sudo --preserve-env=PIPX_DEFAULT_PYTHON pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            [],
            False,
        ),
        (
            "sudo --preserve-env=PATH,PIPX_DEFAULT_PYTHON pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            [],
            False,
        ),
        ("sudo --preserve-env=PATH pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("sudo --preserve-e pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], False),
        ("sudo --preserve pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("sudo PIPX_DEFAULT_PYTHON=/p pipx run x", {}, [], False),
        ("PIPX_DEFAULT_PYTHON=/p sudo pipx run x", {}, [], True),
        ("PIPX_DEFAULT_PYTHON=/p sudo -E pipx run x", {}, [], False),
        ("sudo -Eu nobody pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], False),
        ("sudo -uE pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("sudo -u PIPX_DEFAULT_PYTHON pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("sudo bash -c 'pipx run x'", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("sudo -E bash -c 'pipx run x'", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], False),
        ("/usr/bin/sudo pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("sudo -- pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("sudo -E -- pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], False),
        # env's long options may be shortened too.
        ("env --uns PIPX_DEFAULT_PYTHON pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("env --uns=PIPX_DEFAULT_PYTHON pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("env --ignore-e pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("env --ch /tmp pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], False),
        ("env --chdir=/tmp pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], False),
        ("/usr/bin/env PIPX_DEFAULT_PYTHON=/p pipx run x", {}, [], False),
        # The runner's own Python named by its path chooses nothing.
        ("pipx run --python /usr/bin/python3 x", {}, [], True),
        ("pipx run --python=/usr/bin/python3.12 x", {}, [], True),
        ("pipx run --python /bin/python3 x", {}, [], True),
        ("pipx run --python '/usr/bin/python3' x", {}, [], True),
        ("PIPX_DEFAULT_PYTHON=/usr/bin/python3 pipx run x", {}, [], True),
        ("pipx run x", {"PIPX_DEFAULT_PYTHON": "/usr/bin/python3"}, [], True),
        ("pipx run --python python3.15 x", {}, [], False),
        ("pipx run --python ${{ env.pythonLocation }}/bin/python x", {}, [], False),
        ("pipx run --python /usr/bin/python3 --python /p x", {}, [], False),
        ("pipx run --python /opt/hostedtoolcache/Python/3.15.0/x64/bin/python3 x", {}, [], False),
        # `$'...'` is decoded before it is read.
        ("$'pipx' run x", {}, [], True),
        ("PIPX_DEFAULT_PYTHON=$'' pipx run x", {}, [], True),
        ("PIPX_DEFAULT_PYTHON=$'/usr/bin/python3' pipx run x", {}, [], True),
        ("PIPX_DEFAULT_PYTHON=$'/opt/py/bin/\\x70ython3' pipx run x", {}, [], False),
    ],
)
def test_round_two_pipx_forms(run, env, ids, flagged):
    assert pipx_without_python(run, env, set(ids)) is flagged


def test_a_step_output_given_to_pipx_names_an_earlier_set_up_python_step():
    text = textwrap.dedent(
        """\
        name: x
        on: push
        jobs:
          earlier:
            runs-on: ubuntu-26.04
            steps:
              - id: py
                uses: actions/setup-python@abc
                with: { python-version: "3.15" }
              - name: Scan
                run: pipx run --python ${{ steps.py.outputs.python-path }} checkov -d .
          later:
            runs-on: ubuntu-26.04
            steps:
              - name: Scan
                run: pipx run --python ${{ steps.py.outputs.python-path }} checkov -d .
              - id: py
                uses: actions/setup-python@abc
                with: { python-version: "3.15" }
          not-set-up:
            runs-on: ubuntu-26.04
            steps:
              - id: py
                run: echo "python-path=/x" >> "$GITHUB_OUTPUT"
              - name: Scan
                run: pipx run --python ${{ steps.py.outputs.python-path }} checkov -d .
          uv-only:
            runs-on: ubuntu-26.04
            steps:
              - id: py
                uses: astral-sh/setup-uv@abc
                with: { python-version: "3.15" }
              - name: Scan
                env:
                  PIPX_DEFAULT_PYTHON: ${{ steps.py.outputs.python-path }}
                run: pipx run checkov -d .
          may-be-skipped:
            runs-on: ubuntu-26.04
            steps:
              - id: py
                if: github.event_name == 'push'
                uses: actions/setup-python@abc
                with: { python-version: "3.15" }
              - name: Scan
                run: pipx run --python ${{ steps.py.outputs.python-path }} checkov -d .
          same-condition:
            runs-on: ubuntu-26.04
            steps:
              - id: py
                if: github.event_name == 'push'
                uses: actions/setup-python@abc
                with: { python-version: "3.15" }
              - name: Scan
                if: github.event_name == 'push'
                env:
                  PYTHON_PATH: ${{ steps.py.outputs.python-path }}
                run: pipx run --python "$PYTHON_PATH" checkov -d .
          no-such-step:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-python@abc
                with: { python-version: "3.15" }
              - name: Scan
                env:
                  PYTHON_PATH: ${{ steps.python.outputs.python-path }}
                run: pipx run --python "$PYTHON_PATH" checkov -d .
        """
    )
    assert pipx_problems("x.yml", read_jobs(text)) == [
        "x.yml > later > Scan > pipx",
        "x.yml > not-set-up > Scan > pipx",
        "x.yml > uv-only > Scan > pipx",
        "x.yml > may-be-skipped > Scan > pipx",
        "x.yml > no-such-step > Scan > pipx",
    ]


@pytest.mark.parametrize(
    "text",
    [
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps: [{run: python3 x.py}]\n",
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - {run: python3 x.py}\n",
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - run: echo\n      - python3 x.py\n",
    ],
)
def test_the_reader_refuses_steps_that_are_not_a_block_list_of_block_mappings(text):
    """`steps: [...]` would otherwise read as a job with no steps, and `- {...}` as an empty step."""
    with pytest.raises(AssertionError):
        read_jobs(text)


COMPOSITE = """\
name: sample
description: a sample action
runs:
  using: composite
  steps:
    - name: Script
      shell: bash
      run: |
        python3 x.py
    - uses: actions/setup-python@abc
      with:
        python-version: "3.14"
    - name: Scan
      shell: bash
      run: pipx run checkov -d .
"""


def test_a_composite_action_is_read_as_one_job_of_its_own():
    jobs = read_action(COMPOSITE)
    label = ".github/actions/a/action.yml"
    assert [step.get("name") for step in jobs["composite"]["steps"]] == ["Script", None, "Scan"]
    assert unset_steps(label, jobs, {}) == [f"{label} > composite > Script > python"]
    assert pipx_problems(label, jobs) == [f"{label} > composite > Scan > pipx"]
    assert floor_problems(label, jobs) == [
        f"{label} > composite > step 2 > python: asks for 3.14, below the floor"
    ]
    assert read_action("name: js\nruns:\n  using: node24\n  main: index.js\n") == {}
    assert read_action("name: docker\nruns:\n  using: 'docker'\n  image: Dockerfile\n") == {}
    with pytest.raises(AssertionError):
        read_action("name: x\nruns: {using: composite, steps: [{run: python3 x.py}]}\n")


def test_composite_actions_are_read_with_the_workflows_so_their_keys_can_be_listed(tmp_path):
    """The lists above take keys of composite actions too: `sources` reads .github/actions/<name>/action.yml
    (or .yaml) beside the workflows, and a repository without .github/actions reads only its workflows."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "w.yml").write_text(
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - run: node x.js\n",
        encoding="utf-8",
    )
    assert [label for label, _ in sources(tmp_path)] == ["w.yml"]
    for name in ("a", "b", "c"):
        (tmp_path / ".github" / "actions" / name).mkdir(parents=True)
    (tmp_path / ".github" / "actions" / "a" / "action.yml").write_text(COMPOSITE, encoding="utf-8")
    (tmp_path / ".github" / "actions" / "b" / "action.yaml").write_text(
        COMPOSITE.replace("python3 x.py", "node x.js"), encoding="utf-8"
    )
    (tmp_path / ".github" / "actions" / "c" / "action.yml").write_text(
        "name: js\nruns:\n  using: node24\n  main: index.js\n", encoding="utf-8"
    )
    found = sources(tmp_path)
    assert [label for label, _ in found] == [
        "w.yml",
        ".github/actions/a/action.yml",
        ".github/actions/b/action.yaml",
        ".github/actions/c/action.yml",
    ]
    assert [entry for label, jobs in found for entry in unset_steps(label, jobs, {})] == [
        "w.yml > j > step 1 > node",
        ".github/actions/a/action.yml > composite > Script > python",
        ".github/actions/b/action.yaml > composite > Script > node",
    ]
    assert [entry for label, jobs in found for entry in pipx_problems(label, jobs)] == [
        ".github/actions/a/action.yml > composite > Scan > pipx",
        ".github/actions/b/action.yaml > composite > Scan > pipx",
    ]


FILES = sorted(p for p in WORKFLOWS.iterdir() if p.suffix in (".yml", ".yaml"))
# The workflows and the composite actions (see `sources`), each with its jobs, read once for every test below.
SOURCES = sources(ROOT)
UNSET = [entry for label, jobs in SOURCES for entry in unset_steps(label, jobs)]
FLOOR_PROBLEMS = [problem for label, jobs in SOURCES for problem in floor_problems(label, jobs)]
PIPX_PROBLEMS = [entry for label, jobs in SOURCES for entry in pipx_problems(label, jobs)]


def test_the_reader_finds_every_job_and_step():
    """A guard against the line reader missing a job: every `runs-on:` line belongs to a job it read, and every job it
    read that has steps has at least one. In a composite action, every `- ` item of `runs: steps:` is a step it read."""
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        jobs = read_jobs(text)
        runners = len(re.findall(r"(?m)^\s+runs-on:", text))
        assert len(jobs) >= runners, (
            f"{path.name}: read {len(jobs)} jobs, the file has {runners} runs-on lines"
        )
        steps = len(re.findall(r"(?m)^\s+steps:\s*$", text))
        assert sum(1 for job in jobs.values() if job["steps"]) == steps, path.name
    for label, jobs in SOURCES:
        if label.startswith(".github/actions/") and jobs:
            text = (ROOT / label).read_text(encoding="utf-8")
            items = re.search(r"(?m)^[ \t]+steps:[ \t]*(?:#.*)?\n(?:[ \t]*(?:#.*)?\n)*( *)- ", text)
            assert items, label
            dash = len(items.group(1))
            assert len(jobs["composite"]["steps"]) == len(
                re.findall(rf"(?m)^ {{{dash}}}- ", text)
            ), label


def test_every_set_up_step_asks_for_the_floor_or_newer():
    assert [problem for problem in FLOOR_PROBLEMS if problem not in BELOW_FLOOR_ALLOWED] == []


def test_every_step_that_runs_node_or_python_comes_after_its_version_is_set_up():
    assert [entry for entry in UNSET if entry not in RUNNER_DEFAULT_ALLOWED] == []


def test_every_step_that_runs_pipx_chooses_its_python():
    assert [entry for entry in PIPX_PROBLEMS if entry not in PIPX_ALLOWED] == []


def test_every_allowed_exception_still_exists():
    """So the list cannot hide a step that has since changed, and every entry says why."""
    for entry, reason in RUNNER_DEFAULT_ALLOWED.items():
        assert isinstance(reason, str) and reason.strip(), f"{entry}: an exception needs a reason"
        assert entry in UNSET, entry
    for entry, reason in PIPX_ALLOWED.items():
        assert isinstance(reason, str) and reason.strip(), f"{entry}: an exception needs a reason"
        assert entry in PIPX_PROBLEMS, entry


def test_every_indirect_step_and_below_floor_exception_still_exists_and_has_a_reason():
    """So a renamed or removed step cannot leave either list pointing at nothing."""
    keys = {
        step_key(label, name, step, i, kind)
        for label, jobs in SOURCES
        for name, job in jobs.items()
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
