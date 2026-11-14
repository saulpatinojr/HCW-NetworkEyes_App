"""Every workflow job that runs Node.js or Python chooses its version (saulpatinojr/HCW-HybridCloudWorks#1707).

A job that runs `node`, `npm`, `npx`, `yarn`, `pnpm`, `python3`, `pip`, `pipx`, `pytest`, `uv` or `uvx` without
actions/setup-node or actions/setup-python gets whatever the runner image ships: on ubuntu-26.04 that was Node.js 24 and
Python 3.14 in November 2026, both below the program's floors (Node.js 26, Python 3.15). Nothing else notices, because a
job that names no version has nothing to read. `uv` and `uvx` count as Python, because uv runs the interpreter it finds,
the runner's own unless one was set up; so astral-sh/setup-uv counts as setting Python up only when it is given a
`python-version` at or above the floor. `yarn` and `pnpm` are Node.js programs and count as Node.js; `pytest` and `pipx`
are Python programs and count as Python. pipx builds each tool's virtual environment from `PIPX_DEFAULT_PYTHON` or, when
that is unset, from the interpreter pipx itself runs on (https://github.com/pypa/pipx/blob/main/src/pipx/interpreter.py,
`get_default_python`). GitHub's Ubuntu runner images install pipx with the image's own python3 (`python3 -m pip install
pipx`, actions/runner-images#14654), so after actions/setup-python a `pipx` step still uses the image's Python unless it
is given `--python` (actions/setup-python's `python-path` output) or `PIPX_DEFAULT_PYTHON`. So a step that runs `pipx`
in command position must also choose its interpreter: `--python` among that pipx command's own words (`pipx run --python
"$PYTHON_PATH" ...`), or `PIPX_DEFAULT_PYTHON` set in front of it (`PIPX_DEFAULT_PYTHON=/p pipx ...`) or in the step's,
job's or workflow's `env:` (Copilot on HCW-NetworkEyes_App#393). A step that does not is reported, named; one kept that
way on purpose is listed, with its reason, in PIPX_ALLOWED. The script's own `unset`, `export` and assignments of it are
read too, the last in a shell winning.

What pipx is given must also be the set-up Python. The runner's own Python named by its path (`--python
/usr/bin/python3`, `/usr/bin/python3.12`, `/bin/python3` or the Azure CLI's `/opt/az/bin/python3`, the same as
`PIPX_DEFAULT_PYTHON`) chooses nothing, nor does a command or process substitution this test cannot run (`"$(command
-v python3)"`, `<(...)`) or a `$` the shell passes on as text (`'$P'`, `\\$P`). A `${{ steps.<id>.outputs.python-path }}` value
(only that output: `cache-hit` and `python-version` are not a path) counts only when `<id>` is an earlier
actions/setup-python step of the same job that
is sure to have run first, by the same rules as a set-up step with an `if:` (below); a missing id, a later step, a step
that is not actions/setup-python or one that may be skipped chooses nothing, and so does a `steps` reference written
another way (`steps['py'].outputs`), which names no id this test can read. A shell variable in the value (`--python
"$PYTHON_PATH"`) is read from the step's, job's or workflow's `env:`; one the script sets itself (`P=...`, `for P in`,
`read P`, but not `echo P=...` or `P=/x pipx ...`) counts for the commands after it in the same shell, as does
`$pythonLocation` (setup-python sets it) once an actions/setup-python step, with or without an id, is sure to have
run first, and any other one chooses nothing. A name set in a `-c` script, a shell fed a
heredoc, a `$(...)` or a `( ... )` subshell stays there, and one set outside reaches a child shell only when exported.
A later assignment in the script wins over the `env:` value, and its value is read by the same rules (`P=/usr/bin/python3`
chooses nothing). A bare
`python3.15` still counts, and so does a path under `${{ env.pythonLocation }}`, by the same rule as
`$pythonLocation`. Any other GitHub expression chooses nothing (`${{ github.workspace }}/.venv/bin/python`,
`${{ inputs.python }}`, `${{ env.UNSET }}`), except `${{ env.X }}` and `${{ matrix.X }}`, which are read as GitHub
replaces them, from the step's, job's or workflow's `env:` and from every entry of the job's matrix list, so they
choose when the value they stand for does (Copilot on HCW-NetworkEyes_AddOn#109). A path is read as the shell
resolves it before it is compared, so `/usr/bin/../bin/python3` and `/usr/./bin/python3` are the runner's own
(Copilot on HCW-MigrateOrchestrator_AddOn#75). Settings travel the way the shell passes them: `PIPX_DEFAULT_PYTHON=/p bash -c
'pipx run x'` and `env PIPX_DEFAULT_PYTHON=/p env -S 'pipx run x'` give the inner script the setting, and `sudo` drops
every inherited setting (its default `env_reset`) unless it is given `-E` or `--preserve-env` (bare, or with a list
that names the variable), while `sudo PIPX_DEFAULT_PYTHON=/p pipx ...` sets it.

A command counts when it is in command position on a line of a `run:` step: at the start, after `$(`, `<(`, a backtick,
`(`, `{`, `|`, `&` or `;`, after a `case` pattern at the start of a line (`check)`) or after `case WORD in`, `;;`, `;&`
or `;;&` on the same line, after leading `NAME=value`
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
x')"`); one that hands its script to a container (`"$(docker run img bash -c '...')"`) stays unread. A heredoc or a
here-string given to a shell that reads its script from its input is that shell's script (`bash <<'EOF'`, `bash -s
<<EOF`, `bash <<< 'node x'`), whatever the quoting of the delimiter, since the shell runs it; the same body given to
`cat` is text.

Round 3 (saulpatinojr/HCW-HybridCloudWorks#1707) reads more forms the way the shell and GitHub do. A command named in
quotes (`'node' x.js`, `"node" x.js`, `''node x`) or with a `\\` in it (`\\node x`) is that command, a command's name
ends at an operator as well as a space (`node;`, `x=$(node)`), and `eval` and `builtin` run the words after them. A
quoted `"NAME=..."` given to `env` or `sudo` is an assignment, as env and sudo read it. A runtime run through `sudo`
counts as the runner's own even after a set-up step, because sudo looks its command up on its own fixed list of folders
(`secure_path`); only `sudo env "PATH=$PATH" ...`, which passes the PATH the shell already has, keeps the set-up one,
and a step whose `shell:` runs through sudo runs its whole text that way. A step whose `shell:` (or
`defaults.run.shell`) is a runtime (`python`, `node {0}`) runs it. The outer shell runs only the `$(...)` and backticks
of a double-quoted string, so `bash -c "x; pipx run y $(true)"` runs no `pipx` outside. `unset`, `export -n` (which
takes a name's export away) and `declare +x` are read, and so is a script line that sets PIPX_DEFAULT_PYTHON to a value
that chooses nothing (and, since Copilot's third review, one that chooses, the latest change in a shell winning). sudo
refuses `-i` together with `-E` outright, so `sudo -iE pipx` counts as having no Python chosen. A value given to pipx
chooses nothing when it is a bare name other than the floor's own `python3.15` (PATH would find the runner's), a path
under /usr/local/bin, a path with a `..` after a part this check cannot see, or a pattern or `~` the shell would still
expand; a `\\` in it is dropped first. `${{ env.X }}` is read as GitHub evaluates it, level by level, and `${{
env.pythonLocation }}` stays setup-python's word, which chooses nothing when an `env:` sets `pythonLocation` itself or
the script unsets it.

Copilot's review of the round-3 ports (saulpatinojr/HCW-HybridCloudWorks#1707) reads five more forms, the pre-PR
review of those fixes three more, and Copilot's second round on the ports five more. A `PATH=` in front of a command,
as its assignment or an argument of `env` (`PATH=/usr/bin python3`, `env PATH=/usr/bin node`), that does not start
with the PATH the shell already has (`$PATH`, `${PATH}`) makes the command be looked up on other folders, so it counts
as the runner's own even after a set-up step; `PATH=/x:$PATH` puts /x first and counts the same. So do `env -u PATH`
(`--unset PATH`), `env -i` (`--ignore-environment`, a lone `-`) and `command -p`, which look the command up on the
system's default folders; the last PATH given to env wins, and the shell fills `$PATH` in before env starts, so `env
-i PATH=$PATH node x` keeps the set-up one. A step named in INDIRECT_RUNTIME whose `shell:` runs through sudo or
replaces PATH counts the same, since the script it calls runs under that shell. So does a runtime named by a path in
one of the folders of RUNNER_PYTHON_FOLDERS, which hold the runner image's Node.js too (`/usr/bin/python3`,
`/usr/local/bin/node`), in `run:` or `shell:`, whatever came before it. That rule covers every runtime name, not only
interpreters: `/usr/bin/pipx`, `/usr/local/bin/uv` and `/usr/local/bin/npm` are reported after a set-up step though
`pipx`, `uv` and `npm` are not, because a program in those folders is the runner's own copy or runs on the runner's
own interpreter, and reporting the rare one that is not errs on the safe side. A Python named by a version below the
floor counts the same (`python3.14`); a free-threaded name (`python3.14t`, `python3.15t`) is Python too, its version
read by its number, and a bare `python3t` counts as the runner's, since PATH holds a free-threaded Python only where
one was asked for. A bare name given to pipx counts only when it is the floor's own `python3.15`. The commands of each
clause of a one-line `case` are read (`case "$k" in a) node x ;; esac`), the pattern after `case WORD in`, `;;`, `;&`
or `;;&` set apart. A `${{ matrix.X }}` in the workflow-level `env:` is never the matrix value, since GitHub allows
only `github`, `secrets`, `inputs` and `vars` there, so it chooses nothing and sets nothing up; one in a job's or a
step's `env:` is read as before. The words of a step's `shell:` in front of its shell program act on
PIPX_DEFAULT_PYTHON as the words in front of a `-c` shell do (`shell: env -u PIPX_DEFAULT_PYTHON bash -e {0}` leaves
pipx without the step's setting). A `defaults:` written as a one-line mapping, nested ones included (`defaults: {run:
{shell: "python {0}"}}`), is read whole, and one YAML refuses (a plain value holding a brace, or braces and quotes
that do not balance) stops the check.

Round 4 (saulpatinojr/HCW-HybridCloudWorks#1707) reads two more forms and holds Python to a higher floor. `coproc` runs
the command after it (`coproc node x.js`, `coproc { python3 x; }`); a NAME may come first only before a compound command
(`coproc NAME while node x; do ...`), so in `coproc NAME node x` the command is NAME, as bash reads it (Copilot on
HCW-MigrateOrchestrator_AddOn#77). A step's `shell:` is read as the runner passes it on, not as a shell would read it:
the runner splits the program off at the first space and hands the rest to .NET, which drops double quotes and fills
nothing in (actions/runner ScriptHandler.cs and ScriptHandlerHelpers.cs `ParseShellOptionString`, dotnet/runtime
ProcessUtils.Unix.cs `GetNextArgument`), so `shell: sudo env PATH="$PATH" bash -e {0}` gives env the text `PATH=$PATH`,
which replaces PATH, and a `$X` in a `PIPX_DEFAULT_PYTHON=` there chooses nothing (Copilot on
HCW-MigrateOrchestrator_AddOn#77; see `literal_shell`). Python's floor is the newest patch of its line, 3.15.2, by the
owner's decision of 2026-11-14, so a set-up step that asks for 3.15.0 or 3.15.1, and a command named `python3.15.1`, are
below it, while a line-only `3.15` still stands for the newest and passes. A GitHub expression in `shell:` is read as
one word, as GitHub would fill it in, which no page of GitHub's documentation was found to confirm for `shell:`.

Limits, known and kept: a composite action whose set-up step takes its version from `${{ inputs.* }}` cannot be read,
so it fails closed and needs an entry in BELOW_FLOOR_ALLOWED; these are reported though they need not be, which can
only add findings: a `shell: python` step's text is still read as shell too; an `eval` script is read as a child shell
(a name set but not exported before it is not seen); a `$PATH` written inside double quotes or an unquoted heredoc in
a nested script is read as the inner script's, so `sudo bash -c "sudo env PATH=$PATH node x"` is reported though the
outer shell fills it in first; a folder put in front of `$PATH`, even the set-up one (`PATH=$pythonLocation/bin:$PATH
python3 x`), on purpose; and a version named below the floor (`python3.14`), even where BELOW_FLOOR_ALLOWED lets the
job set that version up. These are not reported: `eval` of a word joined from quoted parts (`eval no'de x'`); a
`--python` path to a Python outside the folders of RUNNER_PYTHON_FOLDERS (`/opt/hostedtoolcache/Python/3.12...`,
`/usr/share/miniconda/bin/python3`); a relative path after `cd` (`cd /usr/bin && pipx run --python ./python3 x`); a
value a `for` loop or `read` sets (`for P in /usr/bin/python3; do ...`), which counts as chosen; a PATH the script
sets in an earlier command (`export PATH=/usr/bin; python3 x`, or `PATH=/usr/bin; python3 x`); a PATH or setting
written to `$GITHUB_PATH` or `$GITHUB_ENV` by an earlier step; the commands of a `case` clause whose pattern holds
parentheses (`@(a|b))`, `?(a))`) or an escaped `)` (`a\\))`, or whose `case` has a subject `$(...)` with spaces or
`in` on the next line; and a set-up version `3` or `3.x` (a major line only), which reads as at the floor. `unset -n
P` is read as unsetting P, which is what bash does unless P is a name reference.

A composite action (`.github/actions/<name>/action.yml`, `runs: using: composite`) is checked like a job of its own,
named `composite`, so its keys read `.github/actions/<name>/action.yml > composite > step name > runtime`. Its steps
run inside the caller's job, but a caller cannot be relied on to have set the runtime up, so the action sets up what it
runs itself. Its findings go into the same lists as a workflow's, and an exception for one goes in the same lists too.

A set-up step with its own `if:` may be skipped while a later command still runs on the runner's own interpreter
(Copilot on HCW-NetworkEyes_AddOn#100), so it covers a later step only when that step's `if:` makes the set-up's true:
the same condition, one of the terms the set-up's condition joins with a top-level `||`, or a condition that joins one
of those with a top-level `&&` and has no top-level `||` of its own (a step under `a && b` runs only when `a` holds, so
a set-up step under `a || c` has run; Copilot on HCW-HybridCloudWorks#1716; but `a && b || d` can run through `d`
alone, so it is not split; Copilot on HCW-NetworkEyes_App#393), or, when the set-up's condition has no top-level
`||`, a condition with no top-level `||` whose `&&` terms include every one of the set-up's (`a && b` covers
`c && a && b`; Copilot on HCW-MigrateOrchestrator_App#117), an `&&` term of the set-up's that joins terms with `||`
counting as included when one of those terms is (`(a || b) && c` covers `a && c`, not `d && c`; Copilot on
HCW-MigrateOrchestrator_App#118). Conditions are compared without a surrounding `${{ }}`, with runs of
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

Each set-up step (a composite action's too, which must have `runs: steps:`) must also ask for the floor or newer
(Copilot on HCW-CloudCrawler_App#81): `python-version` or `python-version-file`, `node-version` or `node-version-file`,
read through `${{ env.X }}` (the step's, job's or workflow's `env:`), `${{ matrix.X }}` (every entry of the job's matrix
list) and the named file, read only when it is a `.python-version`, `.nvmrc` or `.node-version` file at a relative path
inside the checkout with no `..` and no symbolic link on the way. A version that names a line only (`26`, `26.x`,
`3.15`) stands for that line's newest release, so it passes when the line is at or above the floor's; an exact version
(`26.10.0`) must be at or above the floor itself; anything else (`26.11.0-rc.1`, `26.11.0.0`, `lts/*`) cannot be
compared. A value this test cannot work out fails it, naming the step, rather than passing unchecked. A set-up step kept
below the floor on purpose is listed, with its reason, in BELOW_FLOOR_ALLOWED.

This is the Python copy of the check; its JavaScript twin is the website's scripts/workflow-runtime-setup.test.mjs in
HCW-HybridCloudWorks, and the other HCW Python repositories copy this file. The command reading (`_shell_text`,
`runs_runtime`, the patterns above it) and the condition rules (`covers`) behave the same as the JavaScript twin; only
the lists below, which name this repository's workflows, are this repository's own. Keep the logic the same in each
copy and change it in all of them together.

The workflows are read with a small line reader rather than a YAML library, because none is a dependency here. It
relies on the layout every workflow in this repository has (a `jobs:` key at the top level, a `steps:` list, block
`run: |` scripts, `with:` and `env:` written `{ ... }` or as indented `key: value` lines); a file it cannot read that
way fails the test rather than being skipped. A `steps:` written on one line (`steps: [{run: ...}]`) or a step written
as one (`- {run: ...}`) is such a file: the reader stops with an error rather than read the job as having no steps. A
value YAML reads its own way is read that way: null (`~`, `null`, nothing) is empty, a block scalar (`|`, `>-`,
`|2-`, `>-2`) is its text, ending at the first line indented less than its content, a folded one (`run: >-`) folded as
YAML folds it, a double-quoted value with its escapes decoded, a single-quoted one with `''` read as `'`, a comment
after a value dropped (a matrix entry's too), and a plain number in its shortest form (`3.10` is `3.1`, as GitHub hands
it to an action); and a heredoc's delimiter is its whole word (`<<EOF-1`, `<<E"OF"`), its body ending only at a line
that is exactly that word (after leading tabs for `<<-`). `strategy:` or `matrix:` written on one line, a value that
runs over several lines or starts on the line after its key, a quoted key, a space before a key's colon, an anchor,
alias or tag (`&a`, `*a`, `!!str`) and any other line the reader cannot place stop the test too, as the website's
reader stops on them (round 3). A step's keys may follow `-` and any number of spaces, and a matrix list may start at
its key's own indent, as YAML allows.
"""

from __future__ import annotations

import itertools
import posixpath
import re
import textwrap
import time
from decimal import Decimal
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
# (the value plain text, a quoted string, a whole `$(...)`, `$((...))` or backtick pair with no parentheses inside, or
# those run together: `FOO="a b"`, `FOO=$(date) node`) and words that run the next word (`env FOO=1 node`, `sudo node`,
# `if node ...; then`). A plain value holds no `(`, `)` or backtick, so `x=$(sudo pipx run y)` is read from the `$(`,
# not as an assignment whose value runs into the substitution, and no `;`, `&`, `|`, `<` or `>`, which end it
# (`P=/x; pipx ...` is two commands).
ASSIGNMENT = r"""[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\.)*"|'[^']*'|\$\(\([^()`]*\)\)|[$<>]\([^()`]*\)|`[^`]*`|[^\s"'()`;&|<>])*\s+"""
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
# A shell that reads its script from its input: its name and options, none of them `-c` (`bash`, `bash -s`, `sh -e`).
SHELL_READS_INPUT = PATH + rf"(?:ba|da|k|z)?sh(?:\s+{_shell_option('(?:(?!c)[A-Za-z])')})*"
# A here-string given to such a shell (`bash <<< node`) is its script; unquoted, that is the one word after `<<<`.
SHELL_HERE_STRING = SHELL_READS_INPUT + r"\s*<<<\s*"
# After env's options, a lone `-` (the same as `-i`) may come before its assignments and command (`env - node x`;
# Copilot's second round on the ports, HCW-HybridCloudWorks#1707).
ENV_DASH = r"(?:\s+-(?=\s))?"
WRAPPERS = "|".join(
    [
        rf"{PATH}timeout{_options_of(takes, word)}\s+\d+(?:\.\d+)?[smhd]?\s+"
        if word == "timeout"
        else rf"{'' if word == 'exec' else PATH}{word}{_options_of(takes, word)}{ENV_DASH if word == 'env' else ''}\s+"
        for word, takes in WRAPPER_OPTIONS.items()
    ]
    + [
        r"command(?:\s+(?:-p|--(?=\s)))*\s+",
        # `coproc` runs the command after it in the background (round 4, HCW-HybridCloudWorks#1707: Copilot on
        # HCW-MigrateOrchestrator_AddOn#77). A NAME may come first only before a compound command (bash's manual,
        # Coprocesses): `coproc NAME while node x`; before a simple command the first word is the command, so `coproc
        # NAME node x` runs NAME. `{` and `(` open a command anyway.
        r"coproc(?:\s+[A-Za-z_][A-Za-z0-9_]*(?=\s+(?:while|until|if)\s))?\s+",
        r"(?:if|then|else|elif|do|while|until|!)\s+",
        # `eval` runs its arguments as a script (round 3, HCW-HybridCloudWorks#1707): an unquoted first argument is in
        # command position. `builtin` runs the builtin named next (`builtin eval node x`).
        r"(?:eval(?:\s+--(?=\s))?|builtin)\s+",
        SHELL_C,
        SHELL_HERE_STRING,
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
# A runtime's command names. yarn and pnpm are Node.js programs; pytest and pipx are Python programs, so they run on
# the interpreter they were installed with, which is the runner's own unless a set-up step came first (pipx also builds
# each tool's virtual environment from that interpreter unless it is given `--python`).
RUNTIME_NAMES = {
    "node": r"(?:node|npm|npx|yarn|pnpm)",
    "python": r"(?:python(?:3(?:\.\d+){0,2}t?)?|pip3?|pipx|pytest|uvx?)",
}
# Where a command's name ends: a space, the end of the line, or an operator (`node;`, `x=$(node)`, `python3<<EOF`,
# `'npx'|cat`; round 3 review, HCW-HybridCloudWorks#1707).
NAME_END = r"(?=[\s;&|()<>]|$)"
# A runtime command in command position, with the words in front of it (see `_runtime_commands`).
RUNTIME = {
    kind: re.compile(rf"(?P<before>{START}){PATH}{names}{NAME_END}")
    for kind, names in RUNTIME_NAMES.items()
}
# The runtimes this check reads, by kind.
COMMAND = RUNTIME
# A shell in command position given a script with `-c` (`bash -c '...'`, `sh -euo pipefail -c "..."`, `sudo bash -lc
# '...'`, `bash -c -- '...'`, `bash -ec'...'`): the script runs on the runner too, so its commands count. The same
# words after `docker run image` are not in command position, so a container's script stays unread.
SHELL_SCRIPT = re.compile(START + PATH + SHELL_UP_TO_C + rf"(?:{SHELL_AFTER_C})?$")
# The same for a quoted here-string given to a shell that reads its script from its input (`bash <<< 'node x'`), and
# for a heredoc given to one (`bash <<'EOF'`, `bash -s <<EOF`), read where the `<<` starts.
HERE_STRING_SCRIPT = re.compile(START + SHELL_HERE_STRING + "$")
HEREDOC_SCRIPT = re.compile(START + SHELL_READS_INPUT + r"\s*$")
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
# `eval` in command position, with any arguments before this one: eval joins its arguments and runs them as a script,
# so a quoted argument is read like a `-c` script (`eval 'node x'`, `eval echo 'a; node x'`; round 3,
# HCW-HybridCloudWorks#1707).
EVAL_SCRIPT = re.compile(START + r"eval(?:\s+[^\s;&|()<>]+)*\s+$")
# The words after `env` or `sudo` (with their options and assignments), where a quoted `"NAME=..."` is still an
# assignment: env and sudo read their arguments after the shell has taken the quotes off, so `sudo env "PATH=$PATH"
# python3` runs python3 with that PATH (round 3 review, HCW-HybridCloudWorks#1707). At the start of a command a quoted
# `"NAME=..."` is the command's name, not an assignment, and PREFIX_ONLY (the line ends in the words in front of a
# command) tells the two apart.
AFTER_ENV_OR_SUDO = re.compile(
    r"(?:^|[\s;&|(`])"
    + PATH
    + r"(?:env"
    + _options_of(WRAPPER_OPTIONS["env"], "env")
    + ENV_DASH
    + r"|sudo"
    + _options_of(WRAPPER_OPTIONS["sudo"], "sudo")
    + r")\s+(?:"
    + ASSIGNMENT
    + r")*$"
)
PREFIX_ONLY = re.compile(START + "$")
# What a line must hold for each form `_shell_text` reads a quoted script or assignment after, so that a line without it
# is not searched for that form: `sh` for a shell given `-c`, a here-string or a heredoc (SHELL_SCRIPT,
# HERE_STRING_SCRIPT, HEREDOC_SCRIPT); `env` and a last word starting with `-` for ENV_SPLIT_SCRIPT, whose `-S` or
# `--split-string` ends it; `eval` for EVAL_SCRIPT; and `env` or `sudo` for AFTER_ENV_OR_SUDO. Each is a word or an
# ending the form itself needs, and setting `case` patterns apart only writes `;` and spaces, so skipping a line without
# it changes nothing found, while a long line of quoted words stays fast (pre-PR review of Copilot's round-3 port
# fixes, HCW-HybridCloudWorks#1707: a one-line `case` of 1,000 clauses took 38 seconds).
SHELL_WORD = re.compile("sh")
EVAL_WORD = re.compile("eval")
ASSIGNMENT_WORDS = re.compile("env|sudo")


def _last_word_is_option(text: str) -> bool:
    """True when the last word of `text` (a run of characters that are not `\\s`) starts with `-` (see SHELL_WORD)."""
    end = len(text)
    while end > 0 and re.match(r"\s", text[end - 1]):
        end -= 1
    begin = end
    while begin > 0 and not re.match(r"\s", text[begin - 1]):
        begin -= 1
    return begin < end and text[begin] == "-"


QUOTED_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
# `pipx` in command position, with what comes before it (its assignments and wrappers) and its words, up to the end
# of the command (`;`, `&`, `|` or `)`). It has chosen its interpreter when `--python` is one of pipx's own options
# (see `_pipx_option_chooses_python`) or `PIPX_DEFAULT_PYTHON` is one of the assignments in front of it.
PIPX = re.compile(rf"(?P<before>{START}){PATH}pipx{NAME_END}(?P<words>[^;&|)]*)")
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
# The escapes `$'...'` turns into other characters: these, `\xHH`, `\x{H...}`, `\uHHHH`, `\UHHHHHHHH` and octal
# `\NNN` (see `_ansi_c`); any other `\x` is left as it is.
ANSI_C = {"n": "\n", "t": "\t", "'": "'", '"': '"', "\\": "\\"}
ANSI_C_ESCAPE = re.compile(
    r"\\(x\{[0-9A-Fa-f]*\}?|x[0-9A-Fa-f]{1,2}|u[0-9A-Fa-f]{1,4}|U[0-9A-Fa-f]{1,8}|[0-7]{1,3}|.)",
    re.DOTALL,
)
# A quoted string that is one plain word once the shell has read it (`$'\x70ython3'` is `python3`), written as that
# word, so it is read in command position like any other.
PLAIN_WORD = re.compile(r"[A-Za-z0-9_./+:@%,-]+")
# The characters a quoted value keeps when `_shell_text` is asked for values (the pipx check); any other becomes `_`, so
# the value stays one word and opens nothing. A `${NAME}` in it is first written `$NAME` (see VARIABLE).
VALUE_UNSAFE = re.compile(r"[^A-Za-z0-9_./:@%+,=$\x03-]")
# A `$` the shell passes on as text (inside single quotes or `$'...'`, or after a `\\`), written so for the pipx check:
# no variable is read from it, and a value holding one chooses nothing (Copilot on HCW-NetworkEyes_App#395).
LITERAL_DOLLAR = "\x03"
# A shell variable in a value (`"$PYTHON_PATH"`, `${PYTHON_PATH}`), read from the step's, job's or workflow's `env:`.
VARIABLE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
# A GitHub expression (`${{ steps.py.outputs.python-path }}`), which GitHub replaces before the shell starts. For the
# pipx check it is written as one word (see `_gha_tokens`).
GHA_EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)
# The two GitHub expressions a value given to pipx may hold and still choose its Python: setup-python's
# `python-path` output (`steps.py.outputs.python-path`, or `steps.py.outputs['python-path']`) and
# `env.pythonLocation`. `_gha_tokens` writes each as one fixed word (STEP_OUTPUT, PYTHON_LOCATION) and any other
# expression as OTHER_EXPRESSION, which chooses nothing: one written another way (`steps['py'].outputs`), naming
# another output (`cache-hit`, or `python-version`, which is a version, not a path; Copilot on
# HCW-NetworkEyes_App#395) or any other context (`github.workspace`, `inputs.python`; Copilot on
# HCW-NetworkEyes_AddOn#109). A plain mention of `steps` outside an expression chooses nothing either.
PYTHON_PATH_EXPRESSION = re.compile(
    r"steps\.([A-Za-z0-9_-]+)\.outputs(?:\.python-path|\[\s*(['\"])python-path\2\s*\])", re.I
)
STEP_OUTPUT = re.compile(r"__gha__steps\.([A-Za-z0-9_-]+)\.outputs\.python-path__")
PYTHON_LOCATION = "__gha__env.pythonLocation__"
OTHER_EXPRESSION = "__gha__other__"
STEPS = re.compile(r"(?<![A-Za-z0-9.-])steps(?![A-Za-z0-9-])", re.I)
# A GitHub expression that reads the step's, job's or workflow's `env:` or the job's matrix (`${{ env.PY }}`,
# `${{ matrix.python }}`), which GitHub replaces with that value before the shell starts (see `_expansions`).
ENV_OR_MATRIX = re.compile(r"\$\{\{\s*(env|matrix)\.([A-Za-z0-9_-]+)\s*\}\}")
# The variables a value may name without the step's `env:` setting them: actions/setup-python sets `pythonLocation`,
# so it counts only after an actions/setup-python step that is sure to have run (Copilot on
# HCW-NetworkEyes_AddOn#109).
SET_UP_VARIABLES = {"pythonLocation"}
# Stands for a value the script sets itself, in the names `_chooses` reads.
SCRIPT_SET = object()
# Stands for a name the script removes (`unset P`), in the records `_names_view` reads (round 3,
# HCW-HybridCloudWorks#1707).
UNSET = object()
# The names a script itself sets, whose values this check does not follow, so a value naming one still counts. They are
# read only where the shell sets a variable (Copilot on HCW-NetworkEyes_App#395), at the start of a command: a command
# made only of assignments (`P=/x;`; `P=/x pipx ...` sets P for pipx alone, after `$P` was read), `export`, `declare`,
# `local`, `readonly` or `typeset` with assignments, `for P in` or `select P in`, `read P` (`read -a P`) and `unset P`
# (round 3), those builtins with assignments in front of them too (`FOO=1 unset P`: bash still runs the builtin, and,
# outside POSIX mode, keeps FOO for that one command only, so FOO is not read as set; Copilot on HCW-HybridCloudWorks#1722);
# never an argument (`echo P=/x`), quoted text, a comment or a heredoc's body, which `_shell_text` has already set apart.
ASSIGNED_WORD = (
    r"""([A-Za-z_][A-Za-z0-9_]*)\+?=(?:"(?:[^"\\]|\\.)*"|'[^']*'|\$\(\([^()`]*\)\)|[$<>]\([^()`]*\)|`[^`]*`"""
    r"""|[^\s"'()`;&|<>])*"""
)
ONE_ASSIGNMENT = re.compile(ASSIGNED_WORD + r"\s*")
NAMES_SET = re.compile(
    r"(?:^|[$<]\(|[`({|;&]|(?<![^\s])(?:then|do|else|elif|if|while|until|!))\s*"
    r"(?:(?:"
    + ASSIGNMENT
    + r")*(?:(?P<keyword>export|declare|local|readonly|typeset)(?![A-Za-z0-9_=])"
    r"(?P<flags>(?:\s+[-+][A-Za-z]+)*)"
    r"(?P<declared>(?:\s+[^\s;&|)]+)*)"
    r"|(?:for|select)\s+(?P<loop>[A-Za-z_][A-Za-z0-9_]*)"
    r"|read(?![A-Za-z0-9_=])(?P<read>(?:[ \t]+[^\s;&|)]+)*)"
    r"|unset(?![A-Za-z0-9_=])(?P<unset>(?:[ \t]+[^\s;&|)]+)*))"
    r"|(?P<assigned>(?:" + ASSIGNED_WORD.replace("(", "(?:", 1) + r"\s*)+)(?=$|[;&|)}]))"
)
# `read`'s options that take a value; `-a` names the array it sets.
READ_VALUE_OPTIONS = "adinNptu"
# The folders that hold a Python the runner image ships (its own, and the Azure CLI's at /opt/az/bin), and a path to
# one of them, which pipx would use instead of the set-up one (a doubled `/` is read as one; Copilot on
# HCW-HybridCloudWorks#1719). /usr/local/bin is one too (round 3, HCW-HybridCloudWorks#1707): actions/setup-python never
# puts its Python there, while the runner image installs pip's console scripts (pipx among them, run by
# /usr/bin/python3) there and makes the folder writable by every user (images/ubuntu/scripts/build/install-python.sh
# and install-nodejs.sh in actions/runner-images).
RUNNER_PYTHON_FOLDERS = ("/usr/bin", "/bin", "/opt/az/bin", "/usr/local/bin")
SYSTEM_PYTHON = re.compile(
    "(?:"
    + "|".join(folder.replace("/", "/+") for folder in RUNNER_PYTHON_FOLDERS)
    + r")/+python(?:3(?:\.\d+)*t?)?"
)
SETUP = {
    "node": re.compile(r"^actions/setup-node@"),
    "python": re.compile(r"^actions/setup-python@"),
}
# astral-sh/setup-uv sets Python up only when given a `python-version` (see `sets_up`).
SETUP_UV = re.compile(r"^astral-sh/setup-uv@")

# The lowest versions a set-up step may ask for. The program's floors are kept in scripts/version-floors.json in
# HCW-HybridCloudWorks; change them there first, then here.
PYTHON_FLOOR = (3, 15, 2)
NODE_FLOOR = (26, 11, 0)
FLOORS = {"python": PYTHON_FLOOR, "node": NODE_FLOOR}
# The one bare interpreter name that chooses a Python at or above the floor wherever it is found on PATH: the floor's
# own `python3.15` (round 3, HCW-HybridCloudWorks#1707). Any other bare name (`python3`, `python`, `python3.14`, a
# version like `3.15`) is looked up on PATH, which finds the runner's own Python when no set-up step has run first.
FLOOR_PYTHON_NAME = f"python{PYTHON_FLOOR[0]}.{PYTHON_FLOOR[1]}"
# The job statuses a step can run after, and the status functions that name them.
STATUSES = {"success", "failure", "cancelled"}
STATUS_CALL = re.compile(r"(!?)\s*\b(always|failure|cancelled|success)\(\s*\)")
# The set-up step's inputs that name the version, directly or through a file in the repository.
VERSION_INPUTS = {
    "python": ("python-version", "python-version-file"),
    "node": ("node-version", "node-version-file"),
}


# A heredoc's delimiter: the whole shell word after `<<` or `<<-` (`EOF`, `EOF-1`, `END.txt`, `'EOF X'`, `E"OF"`).
HEREDOC_WORD = re.compile(
    r"""<<-?[ \t]*((?:'[^']*'|"(?:[^"\\]|\\.)*"|\\.|[^\s;&|<>()'"\\])+)""", re.DOTALL
)


def _heredoc_word(run: str, at: int) -> tuple[str, bool, int, bool] | None:
    """The heredoc that `<<` at `at` starts: its delimiter with the quotes and backslashes taken out, whether any part
    of it was quoted or escaped (then the body is text the shell does not expand), where the word ends, and whether it
    is `<<-` (then leading tabs are dropped from the body's lines); None when no word follows."""
    found = HEREDOC_WORD.match(run, at)
    if not found:
        return None
    word = found[1]
    delimiter = re.sub(
        r"""'([^']*)'|"((?:[^"\\]|\\.)*)"|\\(.)""",
        lambda m: (
            m[1]
            if m[1] is not None
            else re.sub(r'\\([\\"$`])', r"\1", m[2])
            if m[2] is not None
            else m[3]
        ),
        word,
        flags=re.DOTALL,
    )
    return delimiter, bool(re.search(r"['\"\\]", word)), found.end(), found[0].startswith("<<-")


def _ends_heredoc(line: str, delimiter: str, tabs: bool) -> bool:
    """True when a body line ends its heredoc: the line is exactly the delimiter, after its leading tabs for `<<-`
    (bash does not end one at ` EOF` or `EOF `; Copilot on HCW-NetworkEyes_App#395)."""
    return (line.lstrip("\t") if tabs else line) == delimiter


def _skip_heredoc_bodies(run: str, at: int, heredocs: list[tuple[str, bool]]) -> int:
    """Where the text continues after the bodies of these heredocs (delimiter, `<<-`), which start at `at` (just after
    a new line): each body ends at a line that ends it (see `_ends_heredoc`)."""
    k, n = at, len(run)
    for delimiter, tabs in heredocs:
        while k < n:
            end = run.find("\n", k)
            end = n if end == -1 else end
            text, k = run[k:end], end + 1
            if _ends_heredoc(text, delimiter, tabs):
                break
    return k


def _substitution_close(run: str, at: int) -> int:
    """The index of the `)` that closes the `$(` at `at`, or the end of the text: escapes, quoted strings, heredoc
    bodies and the substitutions inside them are skipped, so their quotes and parentheses do not count (`$(cat <<EOF`
    with `it's` in the body). Inside `((...))` a `<<` is a shift."""
    depth, k, n = 0, at + 1, len(run)
    pending: list[tuple[str, bool]] = []  # the heredocs whose bodies start at the next new line
    arithmetic: int | None = None  # the depth an open `((` started at
    while k < n:
        char = run[k]
        if char == "\n" and pending:
            k = _skip_heredoc_bodies(run, k + 1, pending)
            pending = []
        elif run.startswith("<<<", k):
            k += 3
        elif char == "<" and run.startswith("<<", k) and arithmetic is None:
            word = _heredoc_word(run, k)
            if word:
                pending.append((word[0], word[3]))
            k = word[2] if word else k + 2
        elif char == "\\":
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
            if arithmetic is None and run.startswith("((", k):
                arithmetic = depth
            depth += {"(": 1, ")": -1}.get(char, 0)
            if arithmetic is not None and depth <= arithmetic:
                arithmetic = None
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
    """The text of a `$'...'` string as the shell reads it: `\\n`, `\\t`, `\\'`, `\\"`, `\\\\`, `\\xHH`, `\\x{H...}`,
    `\\uHHHH`, `\\UHHHHHHHH` and octal `\\NNN` decoded (an octal or `\\x{...}` value keeps its low eight bits, as bash
    5.2 does: `\\560` is `p`), cut at a NUL as bash cuts it, and every character that is not printable ASCII, a tab or
    a new line written `_`, which the shell does not split a word on either."""

    def one(match: re.Match[str]) -> str:
        escape = match[1]
        if escape.startswith("x{"):
            return chr(int((escape[2:].rstrip("}") or "0")[-2:], 16))
        if escape[0] in "xuU" and len(escape) > 1:
            code = int(escape[1:], 16)
            return chr(code) if code <= 0x10FFFF else "_"
        if escape[0] in "01234567":
            return chr(int(escape, 8) & 0xFF)
        return ANSI_C.get(escape, match[0])

    text = ANSI_C_ESCAPE.sub(one, body).split("\0", 1)[0]
    return re.sub(r"[^\x20-\x7e\t\n]", "_", text)


def _quoted_text(content: str, mark: str, values: bool) -> str:
    """How `_shell_text` writes a quoted string that runs nothing: `''` (or `""`) when empty, else `'_'` (or `"_"`),
    or, when asked for values, the quotes around the content with every character VALUE_UNSAFE names made `_` (and,
    in single quotes, every `$` written LITERAL_DOLLAR, since the shell reads no variable there)."""
    if not content:
        return mark * 2
    if not values:
        return mark + "_" + mark
    if mark == "'":
        return mark + VALUE_UNSAFE.sub("_", content).replace("$", LITERAL_DOLLAR) + mark
    return (
        mark + VALUE_UNSAFE.sub("_", VARIABLE.sub(lambda m: "$" + (m[1] or m[2]), content)) + mark
    )


def _text_part(literal: str) -> str:
    """How `_shell_text` writes the text between the substitutions of a double-quoted string that runs one: ` _ ` (""
    when there is none), with or without values. The text runs nothing, and a value that holds a substitution chooses
    nothing whatever its text (see `_chooses`). The spaces keep a long string from being one long word, which PATH (a
    run of characters up to a `/`) read again from every place it could start (round 3 review,
    HCW-HybridCloudWorks#1707: 3,000 substitutions took seconds)."""
    return " _ " if literal else ""


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
    # Each heredoc whose body starts at the next new line: its delimiter, whether the shell expands its body, and, when
    # it is given to a shell that reads its script from its input, the words in front of that shell.
    heredocs: list[tuple[str, bool, str | None, bool]] = []
    # Open parentheses inside `$((...))` or `((...))`, where `<<` is a shift; 0 outside.
    arithmetic = 0
    i, n = 0, len(run)

    # Where the current line starts: the part of `out` and the offset in it, and the parts looked at so far (see
    # `line`).
    start = (0, 0)
    seen = 0

    def line() -> str:
        """The text so far on the current line, read back only to the last new line. `out` only grows, so each part is
        looked at once for a new line (a line of 20,000 characters read back part by part for each quoted word took
        seconds; pre-PR review of Copilot's round-3 port fixes, HCW-HybridCloudWorks#1707)."""
        nonlocal start, seen
        for k in range(seen, len(out)):
            at = out[k].rfind("\n")
            if at != -1:
                start = (k, at + 1)
        seen = len(out)
        k, at = start
        return out[k][at:] + "".join(out[k + 1 :]) if k < len(out) else ""

    def quoted(script: str, text: str, following: str = "") -> None:
        """Add a quoted string as `text`; a `-c` script (or an `env -S` value) also as the inner shell reads it. The
        outer reading stays, because the outer shell runs a `$(...)` or backtick in a double-quoted script before the
        inner shell starts (`bash -c "echo '$(node x)'"`). An empty quoted string run together with other text adds
        nothing to its word (`''node x` runs node; round 3 review, HCW-HybridCloudWorks#1707); on its own it is an
        empty word, and stays one."""
        raw = line().lstrip()
        if text in ("''", '""') and (
            re.search(r"[^\s;&|()<>]$", raw) or re.match(r"[^\s;&|()<>]", following)
        ):
            return
        # Read with the line's `case` patterns set apart, so a clause's commands are in command position (see
        # `without_case_patterns`; Copilot's review of the round-3 ports, HCW-NetworkEyes_AddOn#114), and only for the
        # forms whose words the line holds (see SHELL_WORD).
        shell = bool(SHELL_WORD.search(raw))
        split = "env" in raw and _last_word_is_option(raw)
        evaluated = bool(EVAL_WORD.search(raw))
        head = without_case_patterns(raw) if shell or split or evaluated else ""
        found = (
            (shell and (SHELL_SCRIPT.search(head) or HERE_STRING_SCRIPT.search(head)))
            or (split and ENV_SPLIT_SCRIPT.search(head))
            or (evaluated and EVAL_SCRIPT.search(head))
        )
        if not found:
            out.append(text)
        elif values:
            out.append(f"{text}\n\x01{found.group(0)}\n{_shell_text(script, values)}\n\x02\n:")
        else:
            out.append(f"{text}\n{_shell_text(script)}\n:")

    def assigned(at: int) -> str:
        """The `NAME=` of a quoted assignment given to `env` or `sudo` (see AFTER_ENV_OR_SUDO), which is written in
        front of the quotes (`PATH="$PATH"`) so that it reads as the assignment it is; "" for any other quoted string.
        `env -S 'A=1 node x'` is a script to split, not an assignment."""
        name = QUOTED_NAME.match(run, at, at + 256)
        if not name:
            return ""
        raw = line().lstrip()
        if not ASSIGNMENT_WORDS.search(raw):
            return ""
        head = without_case_patterns(raw)
        if AFTER_ENV_OR_SUDO.search(head) and PREFIX_ONLY.search(head):
            return "" if ENV_SPLIT_SCRIPT.search(head) else name[0]
        return ""

    while i < n:
        char = run[i]
        if char == "\\" and i + 1 < n:
            escaped = run[i + 1]
            # A `\` in front of an ordinary character only stands for that character (`\node` is `node`; round 3
            # review).
            out.append(
                " "
                if escaped == "\n"
                else ""
                if escaped == "`"
                else LITERAL_DOLLAR
                if values and escaped == "$"
                else escaped
                if re.fullmatch(r"[A-Za-z0-9_./:@%+,=-]", escaped)
                else run[i : i + 2]
            )
            i += 2
        elif char == "$" and run.startswith("'", i + 1):
            # `$'...'` may hold `\'`, which does not end it.
            j = i + 2
            while j < n and run[j] != "'":
                j += 2 if run[j] == "\\" else 1
            body = _ansi_c(run[i + 2 : j])
            written = body if PLAIN_WORD.fullmatch(body) else _quoted_text(body, "'", values)
            quoted(body, written, run[j + 1 : j + 2])
            i = j + 1
        elif char == "'":
            end = run.find("'", i + 1)
            end = n if end == -1 else end
            name = assigned(i + 1)
            body = run[i + 1 + len(name) : end]
            # A quoted plain word is that word to the shell, so `'node' x` runs node (round 3,
            # HCW-HybridCloudWorks#1707).
            written = body if PLAIN_WORD.fullmatch(body) else _quoted_text(body, "'", values)
            quoted(body, name + written, run[end + 1 : end + 2])
            i = end + 1
        elif char == '"':
            # A command substitution in the string (`$(...)`, or a backtick pair) may hold quotes of its own, and it
            # runs on the runner, so its script is read like any other. Everything else in the string is text to the
            # outer shell, written as `_quoted_text` writes text, so that a `;`, `|` or word in it is not read as a
            # command (round 3, HCW-HybridCloudWorks#1707: `bash -c "x; pipx run y $(true)"` runs no pipx in the outer
            # shell). As text, an escaped backtick prints.
            name = assigned(i + 1)
            j, parts, literal, runs = i + 1 + len(name), [], "", False
            while j < n and run[j] != '"':
                if run[j] == "\\":
                    escape = run[j : j + 2]
                    dollar = values and escape == "\\$"
                    literal += "" if escape == "\\`" else LITERAL_DOLLAR if dollar else escape
                    j += 2
                elif run.startswith("$(", j) and not run.startswith("$((", j):
                    close = _substitution_close(run, j)
                    parts.append(
                        _text_part(literal) + f"$({_shell_text(run[j + 2 : close], values)})"
                    )
                    literal = ""
                    runs, j = True, close + 1
                elif run[j] == "`":
                    close = _backtick_close(run, j)
                    parts.append(
                        _text_part(literal) + f"`{_shell_text(run[j + 1 : close], values)}`"
                    )
                    literal = ""
                    runs, j = True, close + 1
                else:
                    literal += run[j]
                    j += 1
            raw, text = run[i + 1 + len(name) : min(j, n)], literal
            parts.append(_text_part(literal))
            # Given to `-c`, the inner shell runs the script, an escaped backtick included.
            script = re.sub(r"\\([\\\"$`\n])", lambda m: "" if m[1] == "\n" else m[1], raw)
            written = (
                f'"{"".join(parts)}"'
                if runs
                else raw
                if PLAIN_WORD.fullmatch(raw)
                else _quoted_text(text, '"', values)
            )
            quoted(script, name + written, run[j + 1 : j + 2])
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
        elif run.startswith("<<<", i):
            out.append("<<<")
            i += 3
        elif not arithmetic and run.startswith("<<", i):
            word = _heredoc_word(run, i)
            if word:
                # The body is expanded only when no part of the delimiter is quoted or escaped.
                raw = line().lstrip()
                shell = (
                    HEREDOC_SCRIPT.search(without_case_patterns(raw))
                    if SHELL_WORD.search(raw)
                    else None
                )
                heredocs.append((word[0], not word[1], shell.group(0) if shell else None, word[3]))
            out.append("<<")
            i = word[2] if word else i + 2
        elif char == "\n" and heredocs:
            out.append("\n")
            i += 1
            for delimiter, expands, shell, tabs in heredocs:
                body: list[str] = []
                while i < n:
                    end = run.find("\n", i)
                    end = n if end == -1 else end
                    text, i = run[i:end], end + 1
                    if _ends_heredoc(text, delimiter, tabs):
                        break
                    body.append(text)
                script = "\n".join(body)
                if expands:
                    out.extend(f"{command}\n" for command in _heredoc_substitutions(script, values))
                    # What the shell given the body then reads: the body with the outer shell's escapes taken out.
                    script = re.sub(r"\\([\\$`\n])", lambda m: "" if m[1] == "\n" else m[1], script)
                if shell is not None:
                    inner = _shell_text(script, values)
                    out.append(f"\x01{shell}\n{inner}\n\x02\n" if values else f"{inner}\n")
            heredocs = []
        else:
            out.append(char)
            i += 1
    return "".join(out)


# A `case` pattern at the start of a line, whose words are patterns, not commands (`node|npm) ...`).
CASE_PREFIX = re.compile(CASE_PATTERN)
# One word of a `case` line: plain text and quoted strings run together (`"$k"`, `a*`).
CASE_WORD = r"""(?:'[^']*'|"(?:[^"\\]|\\.)*"|[^\s;&|()<>'"])+"""
# `case WORD in`, after which the first clause's pattern follows on the same line.
CASE_START = re.compile(rf"case\s+{CASE_WORD}\s+in(?=\s|$)")
# A clause's pattern after `case WORD in`, `;;`, `;&` or `;;&`: its words joined by `|`, with an optional `(` in
# front (`a)`, `(a|b)`, `node | npm)`).
CLAUSE_PATTERN = re.compile(rf"\s*\(?\s*{CASE_WORD}(?:\s*\|\s*{CASE_WORD})*\s*\)")


def without_case_patterns(line: str) -> str:
    """The line with each `case` pattern on it written as `;` and spaces, the same length, so the commands after it are
    in command position and the pattern's words are not commands: a pattern at the start of the line (`check)`, see
    CASE_PREFIX), and, outside quotes, the pattern after `case WORD in` and after each `;;`, `;&` or `;;&` (`case "$k"
    in a) node x ;; esac` runs node; Copilot's review of the round-3 ports, HCW-NetworkEyes_AddOn#114). A `;;` inside
    quotes ends no clause."""
    # Every pattern ends at a `)`, so a line without one has none (pre-PR review of Copilot's round-3 port fixes,
    # HCW-HybridCloudWorks#1707).
    if ")" not in line:
        return line
    text = line

    def blank(start: int, end: int) -> None:
        nonlocal text
        text = text[:start] + ";" + " " * (end - start - 1) + text[end:]

    i = 0
    leading = CASE_PREFIX.match(line)
    if leading:
        blank(0, leading.end())
        i = leading.end()
    pattern = False  # a clause's pattern may start at `i`
    while i < len(line):
        if pattern:
            pattern = False
            found = CLAUSE_PATTERN.match(line, i)
            if found:
                blank(i, found.end())
                i = found.end()
                continue
        char = line[i]
        if char == "'":
            end = line.find("'", i + 1)
            i = len(line) if end == -1 else end + 1
        elif char == '"':
            j = i + 1
            while j < len(line) and line[j] != '"':
                j += 2 if line[j] == "\\" else 1
            i = j + 1
        elif char == "\\":
            i += 2
        elif char == ";" and line[i + 1 : i + 2] in (";", "&"):
            i += 3 if line.startswith(";;&", i) else 2
            pattern = True
        elif (
            char == "c"
            and (i == 0 or re.match(r"[\s;&|({`]", line[i - 1]))
            and (case := CASE_START.match(line, i))
        ):
            i = case.end()
            pattern = True
        else:
            i += 1
    return text


def _runtime_commands(line: str, kind: str) -> list[re.Match[str]]:
    """Every runtime command of `kind` in command position on a line (see `_pipx_commands`), each with the words in
    front of it. The line is read with its `case` patterns set apart (see `without_case_patterns`), so `node)` names no
    command now that a name may end at `)`, and the commands of each clause of a one-line `case` are found."""
    return _pipx_commands(without_case_patterns(line), RUNTIME[kind])


def runs_runtime(run: str | None, kind: str) -> bool:
    """True when a run script calls the runtime in command position (see `_shell_text` for what is left out)."""
    return any(_runtime_commands(line.strip(), kind) for line in _shell_text(run or "").split("\n"))


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _meaningful(line: str) -> bool:
    return bool(line.strip()) and not line.lstrip().startswith("#")


# A block scalar's indicator (`|`, `>-`, `|2-`, `|-2`), and the plain values YAML reads as null, which GitHub reads as
# an empty string.
BLOCK_SCALAR = re.compile(r"([|>])(?:([+-]?)(\d?)|(\d)([+-]))\s*(?:#.*)?")
NULL = {"", "~", "null", "Null", "NULL"}


# The escapes a double-quoted YAML value may hold, besides `\xHH`, `\uHHHH` and `\UHHHHHHHH`
# (https://yaml.org/spec/1.2.2/#57-escaped-characters).
YAML_ESCAPES = {
    "0": "\0",
    "a": "\a",
    "b": "\b",
    "t": "\t",
    "\t": "\t",
    "n": "\n",
    "v": "\v",
    "f": "\f",
    "r": "\r",
    "e": "\x1b",
    " ": " ",
    '"': '"',
    "/": "/",
    "\\": "\\",
    "N": "\x85",
    "_": "\xa0",
    "L": "\u2028",
    "P": "\u2029",
}


def _number(value: float) -> str:
    """A YAML float written as the website's YAML library (JavaScript's `String`) writes it: `3.10` is `3.1`, `3.0` is
    `3`, `1e3` is `1000`."""
    if value.is_integer() and abs(value) < 1e21:
        return str(int(value))
    if 1e-6 <= abs(value) < 1e21:
        return format(Decimal(repr(value)), "f")
    return re.sub(r"e([-+])0*(\d)", r"e\1\2", repr(value))


def _plain(text: str) -> str:
    """A plain (unquoted) value as YAML 1.2's core schema reads it and GitHub hands it on (round 3,
    HCW-HybridCloudWorks#1707): null (`~`, `null`, nothing) empty, a boolean as `true` or `false`, and a number in its
    shortest form, so an unquoted `3.10` is `3.1`, as GitHub passes it to an action (actions/runner#849; the website's
    YAML library reads it the same way)."""
    if text in NULL:
        return ""
    if text in ("true", "True", "TRUE", "false", "False", "FALSE"):
        return text.lower()
    if re.fullmatch(r"[-+]?[0-9]+", text):
        return str(int(text))
    if re.fullmatch(r"0o[0-7]+|0x[0-9a-fA-F]+", text):
        return str(int(text, 0))
    if re.fullmatch(r"[-+]?\.(?:inf|Inf|INF)", text):
        return "-Infinity" if text.startswith("-") else "Infinity"
    if re.fullmatch(r"\.(?:nan|NaN|NAN)", text):
        return "NaN"
    if re.fullmatch(r"[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?", text):
        return _number(float(text))
    return text


def _scalar(value: str) -> str:
    """A plain or quoted value on one line as YAML reads it (round 3, HCW-HybridCloudWorks#1707): a double-quoted one
    with its escapes decoded (`"\x70ython3 x"` is `python3 x`), a single-quoted one with `''` read as `'`, a comment
    after either dropped, and a plain one read by `_plain`, its comment dropped too. A quoted value that does not close
    on its line, or has text after it, stops the test (this reader does not fold a value over several lines)."""
    text = value.strip()
    if text.startswith('"'):
        out, k = [], 1
        while k < len(text) and text[k] != '"':
            if text[k] == "\\":
                code = text[k + 1 : k + 2]
                size = {"x": 2, "u": 4, "U": 8}.get(code)
                if size:
                    digits = text[k + 2 : k + 2 + size]
                    assert re.fullmatch(rf"[0-9A-Fa-f]{{{size}}}", digits), (
                        f"a bad escape in {value!r}"
                    )
                    out.append(chr(int(digits, 16)))
                    k += 2 + size
                else:
                    assert code in YAML_ESCAPES, f"a bad escape in {value!r}"
                    out.append(YAML_ESCAPES[code])
                    k += 2
            else:
                out.append(text[k])
                k += 1
        assert k < len(text), f"a double-quoted value runs over more than one line: {value!r}"
        decoded, rest = "".join(out), text[k + 1 :]
    elif text.startswith("'"):
        found = re.match(r"'((?:[^']|'')*)'", text)
        assert found, f"a single-quoted value runs over more than one line: {value!r}"
        decoded, rest = found[1].replace("''", "'"), text[found.end() :]
    else:
        text = re.sub(r"\s+#.*$", "", text).strip()
        # An anchor (`&a`), an alias (`*a`) or a tag (`!!str`) is not text: refused, as the website's reader refuses it
        # (round 3 review, HCW-HybridCloudWorks#1707).
        assert not text.startswith(("&", "*", "!")), f"an anchor, alias or tag: {value!r}"
        return _plain(text)
    # A comment after a quoted value needs a space before its `#`, as YAML reads it (`"3.15"#x` is not YAML).
    assert re.fullmatch(r"(?:\s+#.*)?\s*", rest), f"text after a quoted value: {value!r}"
    return decoded


def _folded(text: str) -> str:
    """A `>` block scalar's text as YAML folds it: a line break between two lines at the base indent becomes a space;
    blank lines between them stay line breaks (one fewer); a line indented further keeps the line breaks around it
    (GitHub folds `run: >-` this way, so `echo` and `node x.js` on two lines run `echo node x.js`; Copilot on
    HCW-NetworkEyes_App#395)."""
    lines = text.split("\n")
    out, blanks, more = lines[0], 0, lines[0][:1] in (" ", "\t")
    for line in lines[1:]:
        if line == "":
            blanks += 1
            continue
        indented = line[:1] in (" ", "\t")
        joined = more or indented
        out += ("\n" * (blanks + joined) if blanks else "\n" if joined else " ") + line
        blanks, more = 0, indented
    return out


def _block_text(lines: list[str], indicator: re.Match[str], parent: int) -> str:
    """A block scalar's lines without their indentation: the indentation indicator's (`|2-` is the parent's indent
    plus two) when it has one, so a line indented further keeps the rest, or else the lines' common indentation."""
    digit = indicator[3] or indicator[4]
    # Blank lines before the first line of content are kept, as YAML keeps them; the ones after it go to chomping.
    if not digit:
        return textwrap.dedent("\n".join(lines)).rstrip("\n")
    base = parent + int(digit)
    return "\n".join(line[base:] if line.strip() else "" for line in lines).rstrip("\n")


def _folded_block(text: str) -> str:
    """`_folded` after the blank lines a `>` value starts with, which YAML keeps as they are."""
    body = text.lstrip("\n")
    return text[: len(text) - len(body)] + (_folded(body) if body else "")


def _block_scalar(lines: list[str], indicator: re.Match[str], parent: int) -> str:
    """The text of a block scalar from its indented lines (the key at `parent` spaces): `|` keeps the line breaks, `>`
    folds them (see `_folded`); `-` drops the final line break, and without it one is kept."""
    text = _block_text(lines, indicator, parent)
    if indicator[1] == ">" and text:
        text = _folded_block(text)
    chomp = indicator[2] or indicator[5] or ""
    return text if chomp == "-" or not text else text + "\n"


# Where a quote starts a quoted value: at the start, or after a space, `[`, `{`, `,` or `:` (`it's` is plain text).
QUOTE_STARTS = " \t[{,:"


def _without_comment(text: str) -> str:
    """A one-line value without the comment after it: from a `#` after a space, outside quotes, by the quote rules of
    `_flow_items`, so `["3.15 # floor"]` keeps its `#` (Copilot on HCW-NetworkEyes_App#399)."""
    quote, index = "", 0
    while index < len(text):
        char = text[index]
        if quote:
            if (quote == '"' and char == "\\") or (
                quote == "'" and text[index : index + 2] == "''"
            ):
                index += 1
            elif char == quote:
                quote = ""
        elif char in "'\"" and (index == 0 or text[index - 1] in QUOTE_STARTS):
            quote = char
        elif char == "#" and index > 0 and text[index - 1] in " \t":
            return text[:index].rstrip()
        index += 1
    return text.rstrip()


def _flow_items(inner: str) -> list[str]:
    """The items of a one-line `{ ... }` or `[ ... ]` (its text inside the brackets), split on the commas outside quotes
    and `${{ }}`. Inside double quotes a `\\` takes the next character with it (`"a\\"b"`); inside single quotes `''` is
    a quote, which leaving and entering the quotes again reads the same way (Copilot on HCW-NetworkEyes_App#399). A
    quote starts a quoted value only where QUOTE_STARTS says, so `[it's, b]` is two plain items."""
    parts, depth, quote, start, index = [], 0, "", 0, 0
    while index < len(inner):
        char = inner[index]
        if quote:
            if (quote == '"' and char == "\\") or (
                quote == "'" and inner[index : index + 2] == "''"
            ):
                index += 1
            elif char == quote:
                quote = ""
        elif char in "'\"" and (index == 0 or inner[index - 1] in QUOTE_STARTS):
            quote = char
        elif char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(inner[start:index])
            start = index + 1
        index += 1
    parts.append(inner[start:])
    return [part for part in parts if part.strip()]


def _flow_end(text: str) -> int:
    """Where the `{` that starts `text` is closed, by the quote rules of `_flow_items`; -1 when it is not, or when a
    closer does not match the bracket it closes (`{run: "x"]`; Copilot on HCW-NetworkEyes_App#402)."""
    stack: list[str] = []
    quote, index = "", 0
    while index < len(text):
        char = text[index]
        if quote:
            if (quote == '"' and char == "\\") or (
                quote == "'" and text[index : index + 2] == "''"
            ):
                index += 1
            elif char == quote:
                quote = ""
        elif char in "'\"" and (index == 0 or text[index - 1] in QUOTE_STARTS):
            quote = char
        elif char in "{[":
            stack.append("}" if char == "{" else "]")
        elif char in "}]":
            if not stack or stack.pop() != char:
                return -1
            if not stack:
                return index
        index += 1
    return -1


def _flow_mapping(text: str) -> dict:
    """A one-line `{ key: value, ... }` mapping, split by `_flow_items`. A value that is itself `{ ... }` is read the
    same way, so `defaults: {run: {shell: "python {0}"}}` is read whole (Copilot's second round on the ports,
    HCW-HybridCloudWorks#1707: HCW-CloudAssessor_AddOn#101 and HCW-CloudCrawler_AddOn#79). Braces or quotes that do not
    balance stop the test, and so does a plain value holding `{`, `}`, `[` or `]` (`{ shell: bash -e {0} }`), which YAML
    and the website's reader refuse in a one-line mapping."""
    text = text.strip()
    assert text.startswith("{") and _flow_end(text) == len(text) - 1, (
        f"the braces or quotes of a one-line mapping do not balance: {text!r}"
    )
    pairs = [part.partition(":") for part in _flow_items(text[1:-1])]
    # A quoted key (`{'A': x}`) is refused, as the website's reader refuses it (round 3 review).
    assert not any(key.strip()[:1] in ("'", '"') for key, _, _ in pairs), (
        f"a quoted key in {text!r}"
    )
    found: dict = {}
    for key, _, value in pairs:
        value = value.strip()
        if value.startswith("{"):
            found[key.strip()] = _flow_mapping(value)
            continue
        assert value[:1] in ("'", '"', "[") or not re.search(r"[{}\[\]]", value), (
            f"a plain value with a brace or bracket in a one-line mapping: {value!r}"
        )
        found[key.strip()] = _scalar(value)
    return found


def _block(lines: list[str], at: int, indent: int) -> list[str]:
    """The lines under the key on line `at` (at `indent` spaces), up to the next line at that indent or less."""
    block = []
    for line in lines[at + 1 :]:
        if _meaningful(line) and _indent(line) <= indent:
            break
        block.append(line)
    return block


def _scalar_lines(lines: list[str], at: int, indent: int, indicator: re.Match[str]) -> list[str]:
    """The lines of a block scalar whose key is on line `at` (at `indent` spaces), as YAML reads them: blank lines and
    lines indented at least as far as its content (the indentation indicator's, `|2-` being the key's indent plus two,
    or else the first non-blank line's), up to the first other line. So a comment indented no further than the key, or
    further than the key but less than the content, ends the value rather than being read into it, for a step's
    `run: |` and a block value in `env:` or `with:` alike (round 3, HCW-HybridCloudWorks#1707;
    https://yaml.org/spec/1.2.2/#812-literal-style). A line starting with `#` at the content's indentation is content,
    the first line of it too (YAML 1.2.2, 8.1.1.1 and Example 8.5; Copilot on HCW-NetworkEyes_App#399), and a blank
    line before the first line of content with more spaces than it stops the test, as YAML refuses it."""
    digit = indicator[3] or indicator[4]
    content = indent + int(digit) if digit else None
    block: list[str] = []
    for line in lines[at + 1 :]:
        if line.strip():
            if content is None:
                content = _indent(line)
                assert all(len(blank) <= content for blank in block), (
                    "a block value's leading blank line is indented further than its first line"
                )
            if content <= indent or _indent(line) < content:
                break
        block.append(line)
    return block


def _mapping(lines: list[str], at: int, indent: int) -> dict[str, str]:
    """The mapping under the key on line `at`: a `{ ... }` on the same line, or the `key: value` lines below it, each
    value plain, quoted, null (read as empty, see `_scalar`) or a block scalar (`|`, `>-`, read as its text)."""
    rest = _without_comment(lines[at].split(":", 1)[1]).strip()
    if rest.startswith("{"):
        return _flow_mapping(rest)
    block = _block(lines, at, indent)
    inner = min((_indent(line) for line in block if _meaningful(line)), default=indent + 2)
    found: dict[str, str] = {}
    index = 0
    while index < len(block):
        line = block[index]
        index += 1
        pair = re.match(rf"^ {{{inner}}}([A-Za-z0-9_.-]+):[ \t]*(.*)$", line)
        if not pair:
            # Anything else that is not blank or a comment (a value folded over several lines, a key this reader does
            # not know the form of) stops the test rather than being skipped (round 3, HCW-HybridCloudWorks#1707).
            assert not _meaningful(line), f"cannot read the line {line.strip()!r}"
            continue
        indicator = BLOCK_SCALAR.fullmatch(pair.group(2).strip())
        if indicator:
            scalar = _scalar_lines(block, index - 1, inner, indicator)
            found[pair.group(1)] = _block_scalar(scalar, indicator, inner)
            index += len(scalar)
        else:
            found[pair.group(1)] = _scalar(pair.group(2))
    return found


def _matrix(job: list[str], key_indent: int) -> dict[str, list[str]]:
    """The lists of a job's `strategy: matrix:`, each written `[a, b]` or as `- a` lines; {} when it has none."""
    strategy = [i for i, line in enumerate(job) if re.match(rf"^ {{{key_indent}}}strategy:", line)]
    if not strategy:
        return {}
    # `strategy: {...}` or `matrix: {...}` would read as no matrix: refused, as the website refuses it (round 3,
    # HCW-HybridCloudWorks#1707). `matrix: ${{ fromJSON(...) }}` is a value, not a list, and is read as no lists.
    assert re.fullmatch(r"strategy:\s*(?:#.*)?", job[strategy[0]].strip()), (
        "strategy: is written on one line"
    )
    block = _block(job, strategy[0], key_indent)
    at = [i for i, line in enumerate(block) if re.match(r"^\s+matrix:", line)]
    # Only a block of lists or a `${{ ... }}` expression is read; `matrix: [..]`, `matrix: {..}` or any other value
    # stops the test, as the website's reader stops on it (Copilot on HCW-NetworkEyes_App#399).
    inline = _without_comment(block[at[0]].split(":", 1)[1]).strip() if at else ""
    assert not inline or re.fullmatch(r"\$\{\{.*\}\}", inline), (
        f"matrix: is written on one line: {inline!r}"
    )
    if not at or inline:
        return {}
    matrix_lines = _block(block, at[0], _indent(block[at[0]]))
    inner = min((_indent(line) for line in matrix_lines if _meaningful(line)), default=0)
    found: dict[str, list[str]] = {}
    for index, line in enumerate(matrix_lines):
        match = re.match(rf"^ {{{inner}}}([A-Za-z0-9_-]+):[ \t]*(.*)$", line)
        if not match:
            # A line at the keys' indent that is not a key is a `- ` item of the key above it, read below; anything
            # else stops the test rather than being skipped (Copilot on HCW-NetworkEyes_App#399).
            assert (
                not _meaningful(line)
                or _indent(line) > inner
                or (line.lstrip().startswith("- ") and index > 0)
            ), f"cannot read the matrix line {line.strip()!r}"
            continue
        rest = _without_comment(match.group(2)).strip()
        if rest.startswith("["):
            assert rest.endswith("]"), f"cannot read the matrix list {rest!r}"
            found[match.group(1)] = [_scalar(v) for v in _flow_items(rest[1:-1])]
        else:
            # Each `- value` read as YAML reads it, a comment after it dropped (round 3, HCW-HybridCloudWorks#1707),
            # its `-` indented further than the key or at the key's own indent, as YAML allows (round 3 review).
            items = []
            for item in matrix_lines[index + 1 :]:
                if _meaningful(item) and (
                    _indent(item) < inner
                    or (_indent(item) == inner and not item.lstrip().startswith("- "))
                ):
                    break
                # A line that is neither a `- ` item nor a `key: value` member of an item's mapping (an `include:`
                # entry) continues a value over several lines; the website's YAML reader refuses that too, so this
                # reader stops rather than read part of the value (Copilot on HCW-NetworkEyes_App#399).
                assert (
                    not _meaningful(item)
                    or item.lstrip().startswith("- ")
                    or re.match(r"^\s+[A-Za-z0-9_-]+:(?:\s|$)", item)
                ), f"a matrix value runs over more than one line: {item.strip()!r}"
                items.append(item)
            found[match.group(1)] = [
                _scalar(i.strip()[2:]) for i in items if i.strip().startswith("- ")
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
            # Anything else that is not blank or a comment (a value folded over several lines, a key this reader does
            # not know the form of) stops the test rather than being skipped (round 3, HCW-HybridCloudWorks#1707).
            assert not _meaningful(lines[index - 1]), (
                f"cannot read the line {lines[index - 1].strip()!r}"
            )
            continue
        key, rest = match.group(1), match.group(2)
        if key in ("with", "env"):
            keys[key] = _mapping(lines, index - 1, key_indent)
            index += len(_block(lines, index - 1, key_indent))
        elif indicator := BLOCK_SCALAR.fullmatch(rest):
            block = _scalar_lines(lines, index - 1, key_indent, indicator)
            index += len(block)
            text = _block_text(block, indicator, key_indent)
            keys[key] = _folded_block(text) if indicator[1] == ">" and text else text
        else:
            # Every other value, `run:` and `uses:` included, as YAML reads it (see `_scalar`; round 3,
            # HCW-HybridCloudWorks#1707: `run: "python3 x" # c` is the script `python3 x`).
            keys[key] = _scalar(rest)
    return keys


def _default_shell(lines: list[str], at: int, indent: int) -> str | None:
    """The `run: shell:` of the `defaults:` key on line `at` (at `indent` spaces), written as a block or `{ ... }`;
    None when it names none."""
    rest = _without_comment(lines[at].split(":", 1)[1]).strip()
    if rest.startswith("{"):
        # Read as the nested one-line mapping it is (see `_flow_mapping`), so a quoted `{0}` or comma stays in its
        # value.
        run = _flow_mapping(rest).get("run")
        return run.get("shell") if isinstance(run, dict) else None
    block = _block(lines, at, indent)
    run = [i for i, line in enumerate(block) if re.match(r"^\s+run:", line)]
    if not run:
        return None
    return _mapping(block, run[0], _indent(block[run[0]])).get("shell")


# What a `${{ matrix.X }}` in the workflow-level `env:` is written as: an expression this check cannot read, which
# chooses nothing and sets nothing up (see `_workflow_level`).
WORKFLOW_MATRIX = "${{ matrix in the workflow env: }}"


def _workflow_level(env: dict) -> dict:
    """The workflow-level `env:` as GitHub reads it: only the `github`, `secrets`, `inputs` and `vars` contexts are
    available there (https://docs.github.com/en/actions/reference/workflows-and-actions/contexts), so a
    `${{ matrix.X }}` in it is never the job's matrix value. It is written as WORKFLOW_MATRIX, which fails closed, where
    the job's and the step's `env:` keep the matrix (Copilot's review of the round-3 ports, HCW-HybridCloudWorks#1707:
    HCW-MigrateOrchestrator_AddOn#77). The same rule as the website's `workflowLevel`, which its `stepEnv` applies."""
    return {
        name: (
            ENV_OR_MATRIX.sub(lambda m: WORKFLOW_MATRIX if m[1] == "matrix" else m[0], given)
            if isinstance(given, str)
            else given
        )
        for name, given in env.items()
    }


def read_jobs(text: str) -> dict[str, dict]:
    """Every job of a workflow: {name: {"container": bool, "env": {...}, "matrix": {...}, "shell": str, "steps":
    [{"name", "uses", "run", "if", "with", "env", "shell"}, ...]}}. A job's `env` holds the workflow's `env:` with the
    job's own on top, and its `shell` the job's `defaults: run: shell:`, else the workflow's, else "" (round 3,
    HCW-HybridCloudWorks#1707). A `${{ matrix.X }}` in the workflow's `env:` is never the matrix value (see
    `_workflow_level`)."""
    lines = text.replace("\r\n", "\n").split("\n")
    top_env = [i for i, line in enumerate(lines) if re.match(r"^env:\s*(?:#.*)?$|^env:\s*\{", line)]
    workflow_env = _mapping(lines, top_env[0], 0) if top_env else {}
    top_defaults = [i for i, line in enumerate(lines) if re.match(r"^defaults:", line)]
    workflow_shell = _default_shell(lines, top_defaults[0], 0) if top_defaults else None
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
        env = {
            **_workflow_level(workflow_env),
            **(_mapping(job, env_at[0], key_indent) if env_at else {}),
        }
        defaults_at = [
            i for i, line in enumerate(job) if re.match(rf"^ {{{key_indent}}}defaults:", line)
        ]
        shell = _default_shell(job, defaults_at[0], key_indent) if defaults_at else None
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
            column = (
                dash + 2
            )  # where the current step's keys start: after the `-` and its spaces (`-   run: x`)
            for line in rest:
                if _meaningful(line) and (
                    _indent(line) < dash
                    or (_indent(line) == dash and not line.lstrip().startswith("- "))
                ):
                    break
                if _meaningful(line) and _indent(line) == dash:
                    if current is not None:
                        steps.append(_step_keys(current, column))
                    # The keys start after the `-` and all the spaces after it, as YAML reads `-   run: x` (round 3
                    # review, HCW-HybridCloudWorks#1707).
                    column = dash + 1 + _indent(line[dash + 1 :])
                    # Only a block mapping is read: `- {run: ...}` or `- python3` would read as an empty step.
                    assert column > dash + 1 and re.match(r"[A-Za-z_-]+:(?:\s|$)", line[column:]), (
                        f"job {match.group(1)}: a step is not a block mapping: {line.strip()!r}"
                    )
                    current = [" " * column + line[column:]]
                elif current is not None:
                    current.append(line)
            if current is not None:
                steps.append(_step_keys(current, column))
        jobs[match.group(1)] = {
            "container": container,
            "env": env,
            "matrix": _matrix(job, key_indent),
            "shell": (workflow_shell if shell is None else shell) or "",
            "steps": steps,
        }
    return jobs


def read_action(text: str) -> dict[str, dict]:
    """A composite action's steps (`runs: using: composite`, `runs: steps:`) as one job named `composite`, read by
    `read_jobs` so they are read the same way as a workflow's; {} for any other kind of action (`node24`, `docker`). A
    composite action without `runs: steps:` stops the test with an error rather than read as having none (Copilot on
    HCW-HybridCloudWorks#1719)."""
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
    assert any(re.match(rf"^ {{{inner}}}steps:", line) for line in body), (
        "a composite action has no runs: steps: list"
    )
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
            # A set-up condition with no top-level `||` holds whenever every one of its `&&` terms does, so a later
            # step whose `&&` terms include all of them is covered too (`a && b` covers `c && a && b`; Copilot on
            # HCW-MigrateOrchestrator_App#117).
            every = (
                len(_top_level_terms(rest, "||")) == 1
                and len(_top_level_terms(need, "||")) == 1
                and all(_term_holds(term, _and_terms(need), ran) for term in _and_terms(rest))
            )
            if not (
                rest == ""
                or every
                or any(term in setup_terms and _fixed_term(term, ran) for term in step_terms)
            ):
                return False
    return True


def _term_holds(term: str, terms: list[str], ran: frozenset[str] | set[str] = frozenset()) -> bool:
    """True when the set-up condition's `&&` term `term` surely holds whenever every one of `terms` (the later
    condition's `&&` terms) does: it is one of them, or it joins terms with a top-level `||` and one of those is
    (`a || b` holds when `a` does; Copilot on HCW-MigrateOrchestrator_App#118). The term matched must read only values
    fixed from the set-up step on (`_fixed_term`)."""
    return any(
        option in terms and _fixed_term(option, ran)
        for option in [term, *_top_level_terms(term, "||")]
    )


def _and_terms(expression: str) -> list[str]:
    """The terms a condition with no top-level `||` joins with `&&`, a term in parentheses that itself joins terms with
    `&&` alone opened up: `(a && b) && c` is `a`, `b` and `c`."""
    terms = []
    for term in _top_level_terms(_without_outer_parentheses(expression.strip()), "&&"):
        inner = _top_level_terms(term, "&&")
        nested = len(inner) > 1 and len(_top_level_terms(term, "||")) == 1
        terms.extend(_and_terms(term) if nested else [term])
    return terms


def covers(setup: dict, step: dict, ran: frozenset[str] | set[str] = frozenset()) -> bool:
    """True when a set-up step runs whenever the later step does: it runs after every job status the later step can
    run after, and, status terms aside, it has no `if:`, the same `if:`, or an `if:` whose top-level `||` terms
    include the later step's or one of the terms the later step's joins with a top-level `&&`, reading only values
    fixed from the set-up step on (`ran` holds the ids of the steps before it)."""
    return _conditions_cover(condition(setup), condition(step), ran)


def step_key(file: str, job: str, step: dict, i: int, kind: str) -> str:
    return f"{file} > {job} > {step.get('name') or f'step {i + 1}'} > {kind}"


def _sudo_path(before: str, command: str = "") -> bool | None:
    """What the words in front of a command (`before`) and the command's own word (`command`) do to the PATH it is
    looked up on: True when the runtime found is not the set-up one, because `sudo` replaced PATH with sudo's
    `secure_path` or a `PATH=` replaced it, False when `env` set PATH again after a sudo (`sudo env "PATH=$PATH" node`),
    None when neither. sudo looks its command up on `secure_path` and gives it that PATH even with `-E`, and refuses a
    `PATH=` given to sudo itself (sudo's plugins/sudoers/sudoers.c `set_cmnd_path` and env.c `rebuild_env`), so only a
    later `env` that is given PATH, and then looks the command up itself, passes the set-up PATH on (round 3,
    HCW-HybridCloudWorks#1707). A `PATH=` in front of the command (`PATH=/usr/bin python3`, `env PATH=/usr/bin python3`)
    that does not start with the PATH the shell already has (`PASSES_PATH`) replaces it, so the command is looked up on
    the runner's folders; `PATH=/x:$PATH` puts /x first, so it counts as replaced too. `env -u PATH` (`--unset PATH`),
    `env -i` (`--ignore-environment`, a lone `-`) and `command -p` look the command up on the system's default folders,
    so they replace it as well (pre-PR review of Copilot's round-3 port fixes and Copilot's second round on the ports,
    HCW-HybridCloudWorks#1707), and the last PATH given to env wins. A command named by a path in one of the runner's
    folders, or a Python named by a version below the floor, is not the set-up runtime whatever came before it (see
    `_runner_runtime`; Copilot's review of the round-3 ports, HCW-HybridCloudWorks#1707: HCW-CloudCrawler_App#90,
    HCW-CloudCrawler_AddOn#79 and HCW-NetworkEyes_AddOn#114)."""
    state: bool | None = None
    env = False  # an `env` came after the `sudo`, so a `PATH=` word is its assignment
    options = ""  # "env" or "command" while reading that word's options
    following = ""  # the next word is the value of env's `-u` ("unset") or of another of its options ("skip")
    after_env = False  # the words since an `env` are its options and assignments, so the last `PATH=` among them wins
    for word in (OPENING.sub("", w) for w in WORD.findall(before)):
        bare = word.replace("'", "").replace('"', "")
        if following:
            # `env -u PATH` (`--unset PATH`) leaves the command to be looked up on the system's default folders.
            if following == "unset" and bare == "PATH":
                state = True
            following = ""
            continue
        if re.fullmatch(r"(?:\S*/)?sudo", word):
            state, env, options, after_env = True, False, "", False
            continue
        if re.fullmatch(r"(?:\S*/)?env", word):
            if state is not None:
                env = True
            options, after_env = "env", True
            continue
        if word == "command":
            options, after_env = "command", False
            continue
        # `env -i` (`--ignore-environment`, or a lone `-`) clears PATH, so the command is looked up on the system's
        # default folders too (Copilot's second round on the ports, HCW-HybridCloudWorks#1707: HCW-CloudCrawler_App#90).
        if options == "env" and bare == "-":
            state, options = True, ""
            continue
        # env's options (see `_local_default_python`), and `command -p`, which looks the command up on the system's
        # default folders (pre-PR review of Copilot's round-3 port fixes, HCW-HybridCloudWorks#1707).
        if options == "env" and bare.startswith("-") and bare not in ("-", "--"):
            if bare.startswith("--"):
                name, sign, value = bare[2:].partition("=")
                option = _long_option(name, "env")
                if option == "ignore-environment":
                    state = True
                elif option == "unset" and sign:
                    state = True if value == "PATH" else state
                elif option in ("unset", "chdir") and not sign:
                    following = "unset" if option == "unset" else "skip"
            else:
                for k in range(1, len(bare)):
                    if bare[k] == "i":
                        state = True
                    elif bare[k] in "uCS":
                        value = bare[k + 1 :]
                        if bare[k] != "S" and not value:
                            following = "unset" if bare[k] == "u" else "skip"
                        elif bare[k] == "u" and value == "PATH":
                            state = True
                        break
            continue
        if options == "command" and re.fullmatch(r"-[A-Za-z]+", bare):
            if "p" in bare:
                state = True
            continue
        options = ""
        if not re.match(r"[A-Za-z_][A-Za-z0-9_]*=", bare):
            after_env = False
        # A `PATH=` that does not start with the PATH the shell already has replaces it (Copilot's review of the
        # round-3 ports, HCW-CloudCrawler_App#90).
        if bare.startswith("PATH=") and not PASSES_PATH.match(bare):
            state = True
        # Only the PATH the outer shell had (`PATH=$PATH`, `PATH="$PATH":/x`): `PATH=/usr/bin` finds the runner's own
        # (round 3 review, HCW-HybridCloudWorks#1707). Words with no `sudo` in front of them leave the state to the
        # script around them, whose `$PATH` is sudo's `secure_path` when it runs under sudo.
        elif env and state is not None and PASSES_PATH.match(bare):
            state = False
        # env sets its assignments in order, and the shell has filled `$PATH` in before env starts, so a later
        # `PATH=$PATH` given to env gives the command the shell's PATH again (`env -i PATH=$PATH node`, `env
        # PATH=/usr/bin PATH=$PATH node`; Copilot's second round on the ports, HCW-HybridCloudWorks#1707). Assignments
        # in front of a command are made in order by the shell itself, so there a later `PATH=$PATH` is the earlier
        # one's value and changes nothing.
        elif after_env and PASSES_PATH.match(bare):
            state = None
    return True if _runner_runtime(command) else state


# A `PATH=` that passes on the PATH the shell already has.
PASSES_PATH = re.compile(r"PATH=(?:\$PATH|\$\{PATH\})(?::|$)")


def _runner_runtime(command: str) -> bool:
    """True when a runtime's command word names one that is not the set-up one: a path in one of the runner's folders
    (RUNNER_PYTHON_FOLDERS, which hold the runner image's Node.js too: `/usr/bin/python3`, `/usr/local/bin/node`, read
    as the shell resolves it, see `_chooses`), or a Python named by a version below the floor (`python3.14`,
    `python3.9`; see `_below_floor`), which PATH finds outside the set-up folder (Copilot's review of the round-3 ports,
    HCW-HybridCloudWorks#1707: HCW-CloudCrawler_AddOn#79 and HCW-NetworkEyes_AddOn#114). A name at or above the floor
    (`python3.15`) and a path elsewhere (`.venv/bin/python`, `$pythonLocation/bin/python3`) are left to the words in
    front of it."""
    text = command.replace("'", "").replace('"', "")
    path = re.sub(r"^/+", "/", posixpath.normpath(text)) if text else "."
    # A bare `python3t` is whatever free-threaded Python PATH finds, which a set-up step put there only when it was
    # asked for one (Copilot on HCW-HybridCloudWorks#1723).
    if path == "python3t":
        return True
    head, slash, name = path.rpartition("/")
    if slash and path.startswith("/") and (head or "/") in RUNNER_PYTHON_FOLDERS:
        return True
    version = re.fullmatch(r"python(3(?:\.\d+){1,2})t?", name)
    return version is not None and _below_floor(version[1], "python") is True


def _under(local: bool | None, outer: bool | None) -> bool | None:
    """The PATH a command finds its runtime on, from what the words in front of it do (`local`, see `_sudo_path`) and
    the PATH of the script it is in (`outer`). `$PATH` in `env PATH=$PATH` is that script's PATH, so passing it on
    under a sudo'd script still passes sudo's `secure_path`: `sudo bash -c 'sudo env PATH=$PATH node x'` runs the
    runner's own Node.js (Copilot on the round-3 ports, HCW-HybridCloudWorks#1707)."""
    if local is None:
        return outer
    return local or outer is True


def runs_through_sudo(run: str | None, kind: str, inherited: bool | None = None) -> bool:
    """True when a run script runs the runtime through `sudo` without passing PATH on, or with a replaced PATH or by a
    name that is not the set-up runtime (see `_sudo_path`): `sudo python3 x.py`, `sudo -E node x`, `sudo bash -c 'node
    x'`, `env PATH=/usr/bin python3 x.py`, `/usr/bin/python3 x.py`, `python3.14 x.py`. sudo's `secure_path` holds the
    runner's own Node.js and Python (Ubuntu's and Debian's sudoers set it, and actions/runner-images does not change
    it), not the set-up ones in /opt/hostedtoolcache, so such a step runs the runner's own runtime even after a set-up
    step (round 3, HCW-HybridCloudWorks#1707). A script a sudo'd shell runs (`-c`, a heredoc, `env -S`, `eval`) carries
    the sudo in front of it, and so does a step's whole text when its `shell:` is run through sudo (`inherited`, see
    `step_shell`)."""
    stack: list[bool | None] = [inherited]
    for raw in _shell_text(run or "", values=True).split("\n"):
        line = raw.strip()
        if line.startswith("\x01"):
            stack.append(_under(_sudo_path(line[1:]), stack[-1]))
            continue
        if line.startswith("\x02"):
            stack = stack[:-1] if len(stack) > 1 else stack
            continue
        for found in _runtime_commands(line, kind):
            command = found[0][len(found["before"]) :]
            if _under(_sudo_path(found["before"], command), stack[-1]) is True:
                return True
    return False


def step_shell(step: dict, job: dict) -> str:
    """The command line a step's `run:` text is handed to, as GitHub reads `shell:` (the step's, else the job's or the
    workflow's `defaults.run.shell`, which `read_jobs` keeps as the job's `shell`), with `{0}` written as a word:
    `python` runs `python {0}`, and a custom `node {0}` runs node, so such a step runs that runtime whatever its text
    says (round 3, HCW-HybridCloudWorks#1707;
    https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell). "" for
    the default shell. The same rule as the website's `stepShell`."""
    shell = step["shell"] if "shell" in step else job.get("shell", "")
    return literal_shell(str(shell or ""))


# A word of a `shell:` command that reads the same to a shell as the text it is: no quote, space, `\`, pattern,
# operator or `$` (which `literal_shell` writes as LITERAL_DOLLAR first).
SHELL_SAFE = re.compile(r"[A-Za-z0-9_./+:@%,=\x03-]+")
# The white space .NET's `TrimStart` takes off the front of the arguments (the Latin-1 ones; the rest never appear in a
# one-line `shell:`).
LEADING_SPACE = re.compile(r"^[\t-\r \x85\xa0]+")


def _runner_arguments(text: str) -> list[str]:
    """The words .NET passes a program for an argument string, as dotnet/runtime's ProcessUtils.Unix.cs
    `GetNextArgument` splits it (the Microsoft C runtime's rules): a space or tab outside double quotes ends a word,
    double quotes group and are dropped (`""` inside them is one `"`), backslashes are literal unless they come before a
    `"` (two make one, and an odd one makes the `"` literal), and nothing else is special: no `$`, `~`, pattern or single
    quote. The same rule as the website's `runnerArguments`."""
    words = []
    n = len(text)
    i = 0
    while i < n:
        while i < n and text[i] in " \t":
            i += 1
        if i == n:
            break
        word = ""
        quoted = False
        while i < n:
            slashes = 0
            while i < n and text[i] == "\\":
                i += 1
                slashes += 1
            if slashes:
                if i >= n or text[i] != '"':
                    word += "\\" * slashes
                else:
                    word += "\\" * (slashes // 2)
                    if slashes % 2:
                        word += '"'
                        i += 1
                continue
            char = text[i]
            if char == '"':
                if quoted and i < n - 1 and text[i + 1] == '"':
                    word += '"'
                    i += 1
                else:
                    quoted = not quoted
                i += 1
                continue
            if char in " \t" and not quoted:
                break
            word += char
            i += 1
        words.append(word)
    return words


def literal_shell(shell: str) -> str:
    """A step's `shell:` written as the words the runner starts it with, so the readers above take each word as the text
    it is (round 4, HCW-HybridCloudWorks#1707: Copilot on HCW-MigrateOrchestrator_AddOn#77). The runner runs no shell to
    read `shell:`: it splits the program off at the first space, looks it up on the step's PATH, and hands the rest,
    `{0}` replaced by the script's path and white space taken off its front, to .NET as one argument string
    (actions/runner src/Runner.Worker/Handlers/ScriptHandler.cs and ScriptHandlerHelpers.cs `ParseShellOptionString`),
    which splits it as `_runner_arguments` does. So `sudo env PATH="$PATH" bash -e {0}` gives env the text
    `PATH=$PATH`, and env sets PATH to it. Each `$` is written LITERAL_DOLLAR, so a `PATH=` holding one is a replaced
    PATH (see `_sudo_path`) and a PIPX_DEFAULT_PYTHON holding one chooses nothing (see `_chooses`), and a word with any
    other character a shell would read (a space, a quote, a `\\`, a pattern, an operator) is put in single quotes, a
    `'` in it written `'"'"'`. A GitHub expression is written as one word first (see `_gha_tokens`), as the pipx check
    read it before, and `{0}` as `script`. The same rule as the website's `literalShell`."""
    text = _gha_tokens(shell).replace("{0}", "script")
    if not text:
        return ""
    program, space, rest = text.partition(" ")
    words = [program, *_runner_arguments(LEADING_SPACE.sub("", rest) if space else "")]
    literals = (word.replace("$", LITERAL_DOLLAR) for word in words)
    return " ".join(
        literal if SHELL_SAFE.fullmatch(literal) else "'" + literal.replace("'", "'\"'\"'") + "'"
        for literal in literals
    )


def unset_steps(
    file: str, jobs: dict[str, dict], indirect: dict[str, str] | None = None
) -> list[str]:
    """The steps of one workflow that run a runtime before (or without) setting it up, or through `sudo` (see
    `runs_through_sudo`): "file > job > step > kind". A step needs an earlier set-up step that covers it (see
    `covers`). A step named in `indirect` counts as running its runtime even when its `run:` text does not show it, and
    so does one whose `shell:` runs it (see `step_shell`)."""
    indirect = INDIRECT_RUNTIME if indirect is None else indirect
    found = []
    for name, job in jobs.items():
        if job["container"]:
            continue
        for kind in COMMAND:
            for i, step in enumerate(job["steps"]):
                key = step_key(file, name, step, i, kind)
                shell = step_shell(step, job) if "run" in step else ""
                if not (
                    runs_runtime(step.get("run"), kind)
                    or runs_runtime(shell, kind)
                    or key in indirect
                ):
                    continue
                covered = any(
                    sets_up(earlier, job, kind)
                    and covers(earlier, step, step_ids(job["steps"][:j]))
                    for j, earlier in enumerate(job["steps"][:i])
                )
                # A step named in `indirect` runs its runtime from a script this check does not read, so a `shell:`
                # that runs it through sudo or with a replaced PATH runs that runtime too (Copilot's second round on the
                # ports, HCW-HybridCloudWorks#1707: HCW-CloudCrawler_AddOn#79).
                if (
                    not covered
                    or runs_through_sudo(step.get("run"), kind, _sudo_path(shell))
                    or runs_through_sudo(shell, kind)
                    or (key in indirect and _sudo_path(shell) is True)
                ):
                    found.append(key)
    return found


def _gha_tokens(text: str) -> str:
    """The text with each GitHub expression written as one word: setup-python's `python-path` output as
    `__gha__steps.<id>.outputs.python-path__`, `env.pythonLocation` as PYTHON_LOCATION, and any other expression as
    OTHER_EXPRESSION (see STEP_OUTPUT)."""

    def token(match: re.Match[str]) -> str:
        expression = match[1].strip()
        output = PYTHON_PATH_EXPRESSION.fullmatch(expression)
        if output:
            return f"__gha__steps.{output[1]}.outputs.python-path__"
        return PYTHON_LOCATION if expression == "env.pythonLocation" else OTHER_EXPRESSION

    return GHA_EXPRESSION.sub(token, text)


def _chooses(
    value: str, setup_ids: frozenset[str] | set[str] = frozenset(), env: dict | None = None
) -> bool:
    """True when a value given to pipx as its Python (`--python`, PIPX_DEFAULT_PYTHON) chooses the set-up one: it is
    not empty (quotes aside), not the runner's own Python named by its path (SYSTEM_PYTHON: `/usr/bin/python3`,
    `/bin/python3`, compared once `.`, `..` and doubled `/` are resolved as the shell resolves them), each GitHub
    expression in it is a `steps.<id>.outputs.python-path` this check can read (`steps['py']` is not) or
    `env.pythonLocation`, and each such id is of a step in `setup_ids`, the earlier actions/setup-python steps of the job
    that are sure to have run first (an id-less one is `""` there). `$pythonLocation` and `${{ env.pythonLocation }}`
    count only when `setup_ids` holds one. Given `env` (the step's, job's and workflow's `env:`, and SCRIPT_SET for each name the script
    sets itself), a shell variable in the value is read from it (`--python "$PYTHON_PATH"` with `PYTHON_PATH: ${{
    steps.python.outputs.python-path }}`); one the script sets counts, as does `$pythonLocation`, which
    actions/setup-python sets; any other one is unknown, so the value chooses nothing. Without `env` (an inherited
    value, which GitHub does not expand) the value is read as written. `python3.15` or a path under
    `${{ env.pythonLocation }}` counts. A command substitution (`$(...)`, a backtick) or a `$` the shell passes on as
    text (`'$P'`, `\\$P`) chooses nothing."""
    unknown, located = False, False

    def variable(match: re.Match[str]) -> str:
        nonlocal unknown, located
        name = match[1] or match[2]
        if name in (env or {}):
            given = env[name]
            unknown = unknown or given is UNSET
            return (
                match[0]
                if given is SCRIPT_SET or given is UNSET
                else _gha_tokens("" if given is None else str(given))
            )
        unknown = unknown or name not in SET_UP_VARIABLES
        located = True
        return match[0]

    # The value as the shell passes it on: quotes taken off and a `\` dropped from the character after it
    # (`/usr/bin/pyt\hon3` is `/usr/bin/python3`; round 3, HCW-HybridCloudWorks#1707).
    text = re.sub(r"\\(.)", r"\1", value.replace("'", "").replace('"', ""), flags=re.DOTALL)
    text = (text if env is None else VARIABLE.sub(variable, text)).strip()
    # A `$` passed on as text, or a command or process substitution this check cannot run (`"$(printf
    # /usr/bin/python3)"`, or `<(...)`, which the shell passes as `/dev/fd/N`), is not a Python it can vouch for (Copilot
    # on HCW-NetworkEyes_App#395).
    unreadable = LITERAL_DOLLAR in text or any(sign in text for sign in ("$(", "<(", ">(", "`"))
    # A path is compared as the shell resolves it: `/usr/bin/../bin/python3` and `/usr/./bin/python3` are the
    # runner's (posixpath keeps a leading `//`, which is `/` here; Copilot on HCW-MigrateOrchestrator_AddOn#75).
    path = re.sub(r"^/+", "/", posixpath.normpath(text)) if text else text
    # A value the shell would still expand chooses nothing either, since it is compared before that expansion could
    # turn it into the runner's own Python (round 3, HCW-HybridCloudWorks#1707): a glob or brace (`/usr/bin/python*`,
    # `{a,b}`) or a leading `~` (the runner's home folder).
    expands = re.search(r"[*?\[{}]", VARIABLE.sub("", text)) is not None or text.startswith("~")
    # A `..` after a part this check cannot see (a GitHub expression, a variable) can climb anywhere, the runner's own
    # Python included (`${{ env.pythonLocation }}/../../usr/bin/python3`; round 3, HCW-HybridCloudWorks#1707).
    parts = text.split("/")
    dynamic = next((k for k, part in enumerate(parts) if "__gha__" in part or "$" in part), None)
    climbs = dynamic is not None and ".." in parts[dynamic + 1 :]
    # A value over more than one line (a block value with a `#` line in it, which YAML reads as part of the value) is
    # no interpreter's path (Copilot on HCW-NetworkEyes_App#399).
    several = "\n" in text or "\r" in text
    if (
        not text
        or unknown
        or unreadable
        or expands
        or climbs
        or several
        or SYSTEM_PYTHON.fullmatch(path)
    ):
        return False
    # A bare name is looked up on PATH, which finds the runner's own Python before a set-up step has run, so only the
    # floor's own name counts (FLOOR_PYTHON_NAME; round 3, HCW-HybridCloudWorks#1707).
    if "/" not in text and "$" not in text and "__gha__" not in text:
        return text == FLOOR_PYTHON_NAME
    ids = STEP_OUTPUT.findall(text)
    rest = STEP_OUTPUT.sub("", text)
    located = located or PYTHON_LOCATION in rest
    rest = rest.replace(PYTHON_LOCATION, "")
    return (
        "__gha__" not in rest
        and not STEPS.search(rest)
        and all(found in setup_ids for found in ids)
        and (not located or bool(setup_ids))
    )


def _literal(value: str) -> str:
    """A value a script assigns, as `_chooses` reads it in place of the variable: the text with its quotes taken off.
    So `/usr/bin/python3` chooses nothing, nor does a substitution (`$(command -v python3)`), as when it is given to
    pipx directly; a variable in it (`P="$X"`) is not followed further and counts."""
    return value.replace("'", "").replace('"', "")


def _names_set(found: re.Match[str]) -> tuple[list[tuple[str, object]], bool | str, list[str]]:
    """What one NAMES_SET match sets, read from a line of `_shell_text` with values: each name with its value (see
    `_literal`; SCRIPT_SET, a value this check does not know but counts, for `for`, `read` and `+=`; UNSET for `unset
    P`), whether the command exports them (`export`, `declare -x`, `typeset -x`: True) or takes their export away
    (`export -n`, `declare +x`, `typeset +x`: "unexport"; round 3, HCW-HybridCloudWorks#1707), and the names it only
    exports or unexports (`export P`, `export -n P`)."""
    keyword, flags = found["keyword"] or "", found["flags"] or ""
    exporting = keyword == "export" or (
        keyword in ("declare", "typeset") and re.search(r"(?:^|\s)-[A-Za-z]*x", flags) is not None
    )
    unexporting = (
        keyword == "export" and re.search(r"(?:^|\s)-[A-Za-z]*n", flags) is not None
    ) or (
        keyword in ("declare", "typeset") and re.search(r"(?:^|\s)\+[A-Za-z]*x", flags) is not None
    )
    exported: bool | str = "unexport" if unexporting else exporting
    pairs: list[tuple[str, object]] = []
    marks: list[str] = []
    if found["loop"]:
        pairs.append((found["loop"], SCRIPT_SET))
    for word in (found["declared"] or "").split():
        named = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)(\+?)=(.*)", word, re.DOTALL)
        if named:
            pairs.append((named[1], SCRIPT_SET if named[2] else _literal(named[3])))
        elif exported and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", word):
            marks.append(word)
    # `unset P` removes P, unless it is given `-f` (a function); its other options take no value.
    unset_words = (found["unset"] or "").split()
    if not any(re.match(r"-[A-Za-z]*f", word) for word in unset_words):
        pairs.extend(
            (word, UNSET) for word in unset_words if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", word)
        )
    at, assigned = 0, found["assigned"] or ""
    while (one := ONE_ASSIGNMENT.match(assigned, at)) and one.end() > at:
        text = one[0].rstrip()
        value = text[len(one[1]) :]
        pairs.append((one[1], SCRIPT_SET if value.startswith("+") else _literal(value[1:])))
        at = one.end()
    pending = ""
    for word in (found["read"] or "").split():
        if pending:
            if pending == "a":
                pairs.append((word, SCRIPT_SET))
            pending = ""
        elif word.startswith("-") and len(word) > 1:
            for k in range(1, len(word)):
                if word[k] in READ_VALUE_OPTIONS:
                    if word[k + 1 :] and word[k] == "a":
                        pairs.append((word[k + 1 :], SCRIPT_SET))
                    pending = "" if word[k + 1 :] else word[k]
                    break
        elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", word):
            pairs.append((word, SCRIPT_SET))
    return pairs, exported, marks


def _scope_paths(text: str) -> tuple[list[tuple[int, ...]], dict[int, str]]:
    """For each character of a `_shell_text` reading with values, the shells and subshells it runs in, innermost last,
    and what each one is: "child" for a shell the script starts with its own script (a `-c` or `env -S` script, a
    heredoc or here-string given to a shell: the lines between `\\x01` and `\\x02`), which sees only exported
    variables, and "sub" for a `$(...)`, `<(...)`, backtick pair or `( ... )` subshell, which sees all of them. Neither
    hands the names it sets back out. `$((...))` and `((...))` are arithmetic, not a subshell; a `)` with nothing
    open (a `case` pattern) closes nothing."""
    paths: list[tuple[int, ...]] = []
    kinds: dict[int, str] = {}
    stack: list[list] = []  # [id or None, kind, open parentheses]

    current: tuple[int, ...] = ()  # the ids on `stack`, kept up to date as it changes

    def push(kind: str, depth: int = 0) -> None:
        ident = None
        if kind != "arith":
            ident = len(kinds)
            kinds[ident] = kind
        stack.append([ident, kind, depth])
        settle()

    def settle() -> None:
        nonlocal current
        current = tuple(frame[0] for frame in stack if frame[0] is not None)

    k, n = 0, len(text)
    while k < n:
        char, step = text[k], 1
        top = stack[-1] if stack else None
        if char == "\\":
            step = 2
        elif char == "\x01":
            push("child")
        elif char == "\x02":
            while stack and stack.pop()[1] != "child":
                pass
            settle()
        elif text.startswith("$((", k) or (
            text.startswith("((", k) and not (top and top[1] == "arith")
        ):
            step = 3 if char == "$" else 2
            push("arith", 2)
        elif char in "$<>" and text.startswith("(", k + 1):
            step = 2
            push("sub")
        elif char == "(":
            if top and top[1] == "arith":
                top[2] += 1
            else:
                push("sub")
        elif char == ")":
            if top and top[1] == "arith":
                top[2] -= 1
                if top[2] == 0:
                    stack.pop()
            elif top and top[1] == "sub":
                stack.pop()
                settle()
        elif char == "`":
            if top and top[1] == "tick":
                stack.pop()
                settle()
            else:
                push("tick")
        paths.extend([current] * min(step, n - k))
        k += step
    return paths, kinds


def _names_view(
    env: dict,
    records: dict[str, list[tuple[str, object, tuple[int, ...], bool | str]]],
    here: tuple[int, ...],
    kinds: dict,
    names: set[str] | list[str],
) -> dict:
    """The variables a command at `here` sees: the step's, job's and workflow's `env:` (which GitHub exports), then
    every earlier assignment of the script in this shell or one around it, in order, the last one winning over `env:`
    too (Copilot on HCW-NetworkEyes_App#395); one made outside a child shell reaches into it only when exported (an
    `env:` name stays exported when the script assigns it). An assignment inside a subshell or child shell that has
    ended is not seen (Copilot on HCW-HybridCloudWorks#1719). `records` holds the script's assignments by name, and
    only the names in `names` are worked out, each from its own records, so a long script is not read again in full for
    every command (round 3 review, HCW-HybridCloudWorks#1707: 4,000 lines took seconds); any other name keeps its
    `env:` value."""
    view = dict(env)
    # Names the script has unset or unexported since, so an `env:` name no longer reaches a child shell (round 3,
    # HCW-HybridCloudWorks#1707).
    unexported: set[str] = set()
    for name, value, at, exported in (record for one in names for record in records.get(one, [])):
        if here[: len(at)] != at:
            continue
        crosses = any(kinds[i] == "child" for i in here[len(at) :])
        if value is UNSET or (exported == "unexport" and crosses):
            # An unset `pythonLocation` is no longer the one setup-python set, so it is kept as UNSET for `_chooses`.
            if name in SET_UP_VARIABLES and value is UNSET:
                view[name] = UNSET
            else:
                view.pop(name, None)
            unexported.add(name)
            continue
        if exported == "unexport":
            unexported.add(name)
        elif exported:
            unexported.discard(name)
        if not crosses or exported is True or (name in env and name not in unexported):
            view[name] = value
    return view


def _pipx_commands(line: str, pattern: re.Pattern[str] = PIPX) -> list[re.Match[str]]:
    """Every `pipx` in command position on a line, each read from where it starts: the search goes on from the start
    of each match, not its end, so a `pipx` inside an assignment's `$(...)` is read even when a later command on the
    line took the assignment into its own match (`x=$(sudo pipx run y) PIPX_DEFAULT_PYTHON=/p pipx run z`; Copilot on
    HCW-HybridCloudWorks#1719)."""
    found, at = [], 0
    while (one := pattern.search(line, at)) is not None:
        found.append(one)
        at = one.start() + 1
    return found


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
    preserve = False  # `sudo` was told to keep the whole environment (`-E`, `--preserve-env`)
    named = False  # `sudo` was told to keep PIPX_DEFAULT_PYTHON by name (`--preserve-env=...,PIPX_DEFAULT_PYTHON`)
    login = (
        False  # `sudo -i` (`--login`), which resets the environment whatever `-E` says (round 3)
    )
    for word in (OPENING.sub("", w) for w in WORD.findall(before)):
        # The word as the command receives it: quotes removed (`-u 'PIPX_DEFAULT_PYTHON'`, `--unset="..."`); a `$'...'`
        # string is already decoded by `_shell_text` (Copilot on HCW-NetworkEyes_App#395).
        bare = word.replace("'", "").replace('"', "")
        if following:
            if following == "unset" and bare == "PIPX_DEFAULT_PYTHON":
                chosen = False
            following = ""
            continue
        if wrapper == "sudo" and (word == "--" or not word.startswith("-")):
            # The end of sudo's options: it resets the environment now, unless told to keep the variable.
            chosen = chosen if named or (preserve and not login) else False
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
            wrapper, preserve, named, login = "sudo", False, False, False
        elif wrapper == "sudo" and bare.startswith("--"):
            name, given, value = bare[2:].partition("=")
            option = _long_option(name, "sudo")
            if option == "preserve-env" and not given:
                preserve = True
            elif option == "preserve-env":
                named = named or "PIPX_DEFAULT_PYTHON" in value.split(",")
            elif option == "login":
                login = True
            elif option in WRAPPER_LONG_OPTIONS["sudo"] and not given:
                following = "skip"
        elif wrapper == "sudo":
            for k in range(1, len(bare)):
                if bare[k] == "E":
                    preserve = True
                elif bare[k] == "i":
                    login = True
                elif bare[k] in WRAPPER_OPTIONS["sudo"]:
                    following = "" if bare[k + 1 :] else "skip"
                    break
        elif wrapper != "env" or word == "--":
            wrapper = ""
        elif bare == "-":
            chosen = False
        elif bare.startswith("--"):
            name, given, value = bare[2:].partition("=")
            option = _long_option(name, "env")
            if option == "ignore-environment":
                chosen = False
            elif option == "unset" and given:
                chosen = False if value == "PIPX_DEFAULT_PYTHON" else chosen
            elif option in ("unset", "chdir") and not given:
                following = "unset" if option == "unset" else "skip"
        elif bare.startswith("-"):
            for k in range(1, len(bare)):
                if bare[k] == "i":
                    chosen = False
                elif bare[k] in "uCS":
                    value = bare[k + 1 :]
                    if bare[k] != "S" and not value:
                        following = "unset" if bare[k] == "u" else "skip"
                    elif bare[k] == "u" and value == "PIPX_DEFAULT_PYTHON":
                        chosen = False
                    break
        else:
            wrapper = ""
    if wrapper == "sudo" and not (named or (preserve and not login)):
        chosen = False
    return chosen


def _or_inherited(local: bool | None, inherited: bool) -> bool:
    """The command's own setting when it has one, else the inherited one."""
    return inherited if local is None else local


# A `pythonLocation` the workflow's, job's or step's own `env:` sets: GitHub's value for it may be that one or
# actions/setup-python's, so neither `$pythonLocation` nor `${{ env.pythonLocation }}` chooses then (round 3,
# HCW-HybridCloudWorks#1707).
OWN_LOCATION = "${{ pythonLocation set in env: }}"
LOCATION_EXPRESSION = re.compile(r"\$\{\{\s*env\.pythonLocation\s*\}\}")


def step_env(job_env: dict, own_env: dict) -> dict:
    """The `env` context a step's `with:` and `run:` are read with, as GitHub builds it level by level (round 3,
    HCW-HybridCloudWorks#1707): the workflow's and the job's `env:` (`job_env`, as `read_jobs` merges them), as written
    (GitHub does not allow the `env` context in either, so a `${{ env.X }}` there stays as written and chooses nothing),
    then the step's own `env:` on top, each `${{ env.X }}` in it replaced once by X's value at the job's level (a name
    the step's own `env:` sets is not seen there). `pythonLocation` is left as written: it is actions/setup-python's
    (see `_expansions`). The context availability table:
    https://docs.github.com/en/actions/reference/workflows-and-actions/contexts. The same rule as the website's
    `stepEnv`."""
    evaluated = dict(job_env)
    for name, given in own_env.items():
        evaluated[name] = (
            given
            if given is None
            else ENV_OR_MATRIX.sub(
                lambda m: (
                    ("" if job_env[m[2]] is None else str(job_env[m[2]]))
                    if m[1] == "env" and m[2] != "pythonLocation" and m[2] in job_env
                    else m[0]
                ),
                str(given),
            )
        )
    return evaluated


def _expansions(run: str, env: dict, matrix: dict | None = None) -> list[tuple[str, dict]]:
    """The run script and `env` (the `env` context of `step_env`) as GitHub hands them to the shell, once for each
    combination of the matrix entries the text names: each `${{ matrix.X }}` in a value of `env` replaced by one entry
    of the job's matrix list X, then each `${{ env.X }}` and `${{ matrix.X }}` in the script replaced, once, by that
    value or entry (GitHub does not read an expression again in the text one produced; round 3,
    HCW-HybridCloudWorks#1707). An expression it cannot replace stays, and `_gha_tokens` writes it as one that chooses
    nothing (Copilot on HCW-NetworkEyes_AddOn#109). `${{ env.pythonLocation }}` is never replaced: it stays
    actions/setup-python's word, which `_chooses` reads, or, when `env` sets `pythonLocation` itself, becomes
    OWN_LOCATION."""
    own = "pythonLocation" in env

    def located(text: str) -> str:
        return LOCATION_EXPRESSION.sub(OWN_LOCATION, text) if own else text

    texts = [run, *(str(value) for value in env.values() if value is not None)]
    names = sorted(
        {
            found[2]
            for text in texts
            for found in ENV_OR_MATRIX.finditer(text)
            if found[1] == "matrix" and (matrix or {}).get(found[2])
        }
    )
    expansions = []
    for entries in itertools.product(*((matrix or {})[name] for name in names)):
        entry = dict(zip(names, entries, strict=True))

        def from_matrix(found: re.Match[str], entry: dict = entry) -> str:
            return str(entry[found[2]]) if found[1] == "matrix" and found[2] in entry else found[0]

        values = {
            name: given if given is None else ENV_OR_MATRIX.sub(from_matrix, located(str(given)))
            for name, given in env.items()
        }
        if own:
            values["pythonLocation"] = OWN_LOCATION

        def replace(found: re.Match[str], values: dict = values, from_matrix=from_matrix) -> str:
            if found[1] == "matrix":
                return from_matrix(found)
            if found[2] == "pythonLocation" or found[2] not in values:
                return found[0]
            return "" if values[found[2]] is None else str(values[found[2]])

        expansions.append((ENV_OR_MATRIX.sub(replace, located(run)), values))
    return expansions


def pipx_without_python(
    run: str | None,
    env: dict,
    setup_ids: frozenset[str] | set[str] = frozenset(),
    matrix: dict | None = None,
    shell: str = "",
) -> bool:
    """True when, for any entry of the job's `matrix` the script names, it runs `pipx` with no Python chosen (see
    `_expansions` and `_pipx_without_python_once`). `shell` is the step's `shell:` as `step_shell` writes it: what its
    words in front of the shell program do to PIPX_DEFAULT_PYTHON (`env -u PIPX_DEFAULT_PYTHON bash -e {0}`, `env -i
    bash -e {0}`) is what the script inherits, as for the words in front of a `-c` shell (Copilot's review of the
    round-3 ports, HCW-HybridCloudWorks#1707: HCW-CloudCrawler_App#90)."""
    return any(
        _pipx_without_python_once(text, values, setup_ids, shell)
        for text, values in _expansions(run or "", env, matrix)
    )


def _names_in(text: str) -> set[str]:
    """The shell variables a text names (`$P`, `${P}`), the only ones `_chooses` reads from a view."""
    return {found[1] or found[2] for found in VARIABLE.finditer(text)}


def _pipx_without_python_once(
    run: str, env: dict, setup_ids: frozenset[str] | set[str] = frozenset(), shell: str = ""
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
    variable of the step's `env:` (`--python "$PYTHON_PATH"`), which is read the same way; a variable that neither the
    `env:` nor the script sets chooses nothing. An inherited value is used as written, since GitHub does not expand a
    shell variable in `env:`."""
    stack = [_chooses(_gha_tokens(str(env.get("PIPX_DEFAULT_PYTHON") or "")), setup_ids)]
    # The step's `shell:` starts the script the way a `-c` shell's words start theirs: when its words set, unset or
    # clear PIPX_DEFAULT_PYTHON, the script inherits what they make (Copilot's review of the round-3 ports,
    # HCW-CloudCrawler_App#90).
    from_shell = (
        _local_default_python(_shell_text(_gha_tokens(shell), values=True), setup_ids, env)
        if shell
        else None
    )
    if from_shell is not None:
        stack.append(from_shell)
    text = _shell_text(_gha_tokens(run or ""), values=True)
    scopes: list = []  # `_scope_paths(text)`, worked out the first time a script sets a name

    def view_at(index: int, names: set[str] | list[str]) -> dict:
        """The variables a command at `index` of `text` sees, of those in `names` (see `_names_view`)."""
        if not records:
            return dict(env)
        if not scopes:
            scopes.extend(_scope_paths(text))
        here = scopes[0][index] if index >= 0 else ()
        return _names_view(env, records, here, scopes[1], names)

    def record(name: str, value: object, here: tuple[int, ...], exported: bool | str) -> None:
        records.setdefault(name, []).append((name, value, here, exported))

    def inherited(index: int) -> bool:
        """What a command at `index` inherits for PIPX_DEFAULT_PYTHON: what the shell it runs in (the innermost child
        shell) was started with, then each change the script made to it in that shell, or in a subshell of it that is
        still open, in order, the latest winning (Copilot on HCW-NetworkEyes_App#399): `unset` removes it, `export -n`
        keeps it from the commands the shell starts, `export` gives it to them again, and an assignment changes its
        value. pipx sees the value only while it is exported: in the outermost shell when the step's, job's or
        workflow's `env:` sets it or the script exports it, in a child shell when it was handed one that chooses."""
        state = stack[-1]
        exported = "PIPX_DEFAULT_PYTHON" in env if len(stack) == 1 else state
        if changes:
            here = scopes[0][index] if index >= 0 else ()
            child = max(
                (k for k, ident in enumerate(here) if scopes[1][ident] == "child"), default=-1
            )
            for at, change, choice in changes:
                if len(at) <= child or here[: len(at)] != at:
                    continue
                if change == "unset":
                    state, exported = False, False
                    continue
                exported = {"unexport": False, "export": True}.get(change, exported)
                state = state if choice is None else choice
        return state and exported

    # name -> [(name, value, scope path, exported)], in the order the script sets them
    records: dict[str, list[tuple[str, object, tuple[int, ...], bool | str]]] = {}
    # Each change the script makes to PIPX_DEFAULT_PYTHON, in order (see `inherited`): its scope path, what it does
    # ("unset", "unexport", "export" or "assign"), and whether the value it gives chooses the set-up Python (None when
    # it gives none: `export -n PIPX_DEFAULT_PYTHON`). A value this check does not follow (`read`, `+=`) chooses nothing.
    changes: list[tuple[tuple[int, ...], str, bool | None]] = []
    offset = 0
    for raw in text.split("\n"):
        line = raw.strip()
        lead, offset = offset + len(raw) - len(raw.lstrip()), offset + len(raw) + 1
        if line.startswith("\x01"):
            # A `-c` script (or `env -S` value) starts: it inherits what the words in front of its shell make.
            local = _local_default_python(line[1:], setup_ids, view_at(lead - 1, _names_in(line)))
            stack.append(_or_inherited(local, inherited(lead - 1)))
            continue
        if line.startswith("\x02"):
            stack = stack[:-1] if len(stack) > 1 else stack
            continue
        # In the order the shell meets them: a name the script sets counts from the end of the command that sets it
        # on, in the shell that set it (see `_names_view`); the step's `env:` comes first. A `case` pattern (`pipx)
        # ...`) names no command, so `pipx` is looked for with the patterns set apart (see `without_case_patterns`),
        # which keeps the line's length.
        events = sorted(
            [(found.end(), 0, found) for found in NAMES_SET.finditer(line)]
            + [
                (found.end("before"), 1, found)
                for found in _pipx_commands(without_case_patterns(line))
            ],
            key=lambda event: (event[0], event[1]),
        )
        for at, kind, found in events:
            if kind == 0:
                pairs, exported, marks = _names_set(found)
                if not scopes and (pairs or marks):
                    scopes.extend(_scope_paths(text))
                here = scopes[0][lead + at - 1] if scopes else ()
                change = {"unexport": "unexport", True: "export"}.get(exported, "assign")
                for name, value in pairs:
                    if name == "PIPX_DEFAULT_PYTHON":
                        changes.append(
                            (here, "unset", None)
                            if value is UNSET
                            else (
                                here,
                                change,
                                isinstance(value, str)
                                and _chooses(
                                    value, setup_ids, view_at(lead + at - 1, _names_in(value))
                                ),
                            )
                        )
                    record(name, value, here, exported)
                view = view_at(lead + at - 1, marks) if marks else {}
                for name in marks:
                    if name == "PIPX_DEFAULT_PYTHON":
                        changes.append((here, change, None))
                    if name in view:
                        record(name, view[name], here, exported)
                continue
            view = view_at(lead + at, _names_in(found[0]))
            local = _local_default_python(found["before"], setup_ids, view)
            if not (
                _pipx_option_chooses_python(found["words"], setup_ids, view)
                or _or_inherited(local, inherited(lead + at))
            ):
                return True
    return False


def python_setup_ids(steps: list[dict], i: int) -> set[str]:
    """The ids of the actions/setup-python steps before step `i` that are sure to have run before it (see `covers`),
    the only steps whose outputs choose pipx's Python; one without an id is `""`, which no output names but which
    lets `$pythonLocation` count (Copilot on HCW-NetworkEyes_AddOn#109)."""
    return {
        "" if earlier.get("id") is None else str(earlier["id"])
        for j, earlier in enumerate(steps[:i])
        if SETUP["python"].search(earlier.get("uses", ""))
        and covers(earlier, steps[i], step_ids(steps[:j]))
    }


def pipx_problems(file: str, jobs: dict[str, dict]) -> list[str]:
    """The steps of one workflow that run `pipx` without choosing its interpreter: "file > job > step > pipx", read
    with the step's `shell:` (see `pipx_without_python`). A job in a `container:` is skipped, as `unset_steps` skips
    it."""
    return [
        step_key(file, name, step, i, "pipx")
        for name, job in jobs.items()
        if not job["container"]
        for i, step in enumerate(job["steps"])
        if pipx_without_python(
            step.get("run"),
            step_env(job["env"], step.get("env") or {}),
            python_setup_ids(job["steps"], i),
            job.get("matrix"),
            step_shell(step, job) if "run" in step else "",
        )
    ]


def _resolved(value: str, step: dict, job: dict) -> list[str] | None:
    """The plain values an input stands for: itself, or what `${{ env.X }}` (the `env` context of `step_env`) or
    `${{ matrix.X }}` (every entry of the job's matrix list) holds, a value of `env` that is itself one
    `${{ matrix.Y }}` read as the matrix list Y (GitHub evaluates a job's or step's `env:` with the matrix). None when it
    cannot be worked out here. The same rule as the website's `resolved`."""
    found = re.fullmatch(r"\$\{\{\s*(env|matrix)\.([A-Za-z0-9_-]+)\s*\}\}", value.strip())
    if not found:
        return None if "${{" in value else [value.strip()]
    source, name = found.groups()
    if source == "env":
        env = step_env(job.get("env", {}), step.get("env") or {})
        if name not in env:
            return None
        given = "" if env[name] is None else str(env[name]).strip()
        matrix = re.fullmatch(r"\$\{\{\s*matrix\.([A-Za-z0-9_-]+)\s*\}\}", given)
        if not matrix:
            return None if "${{" in given else [given]
        name = matrix[1]
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
    if len(paths) != 1 or (path := _version_file(root, paths[0])) is None:
        return None
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")] or None


# The version files this test reads: the names the website's `scripts (operations)` change filter matches wherever they
# are, so a change to one runs this test (Copilot on HCW-HybridCloudWorks#1719). Any other name is not read, so its
# set-up step is reported as asking for a version this test cannot work out, and needs an entry in BELOW_FLOOR_ALLOWED.
VERSION_FILE_NAMES = (".python-version", ".nvmrc", ".node-version")


def _version_file(root: Path, given: str) -> Path | None:
    """The version file a set-up step names, when this test may read it: a path relative to `root` with no `..` and
    no symbolic link on the way, to a regular file whose name is in VERSION_FILE_NAMES; None otherwise, so the step is
    reported (Copilot on HCW-HybridCloudWorks#1719: a composite action's `../../proc/self/environ` must not be
    read)."""
    parts = given.replace("\\", "/").split("/")
    if not given or given.startswith("/") or ".." in parts or parts[-1] not in VERSION_FILE_NAMES:
        return None
    path = root
    for part in (part for part in parts if part not in ("", ".")):
        path = path / part
        if path.is_symlink():
            return None
    return path if path.is_file() else None


def _below_floor(version: str, kind: str) -> bool | None:
    """True when the version is under the floor, False when at or above it, None when it is not one of the forms this
    test reads: `N`, `N.x` and `N.M` name a line and mean its newest release, so only their numbers are compared with
    the floor's (`26` with 26, `3.15` and `3.15.x` with 3.15; Copilot on HCW-HybridCloudWorks#1719); `N.M.P` is exact and compared in full. Anything else, trailing text
    included (`26.11.0-rc.1`, `26.11.0.0`, `lts/*`), is None, so the floor test names the step."""
    # A free-threaded Python (`3.14t`, `3.15.1t`) is compared by its number (pre-PR review of Copilot's round-3 port
    # fixes, HCW-HybridCloudWorks#1707).
    text = version.strip()
    found = re.fullmatch(
        r"v?(\d+)(?:\.x|\.(\d+)(?:\.x|\.(\d+))?)?",
        re.sub(r"(\d)t$", r"\1", text) if kind == "python" else text,
    )
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
    (tmp_path / "old").mkdir()
    (tmp_path / "old" / ".python-version").write_text("3.14\n", encoding="utf-8")
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
                with: { python-version-file: old/.python-version }
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
        # A job's `env:` cannot read the `env` context, so `${{ env.OLD }}` there stays unread (round 3).
        "x.yml > through-env > step 1 > python: cannot work out the version it asks for",
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
        # Below the floor since it moved to 3.15.2 (owner decision 2026-11-14, HCW-HybridCloudWorks#1707).
        ("3.15.0", "python", True),
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
        ('pipx run --python "$P" tool', {"P": "/opt/py/bin/python3"}, False),
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
        ('PIPX_DEFAULT_PYTHON="$P" pipx run x', {"P": "/opt/py/bin/python3"}, False),
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
        ('pipx run --python "$P" --spec x x', {"P": "/opt/py/bin/python3"}, False),
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
        ("pipx run --python ${{ env.pythonLocation }}/bin/python x", {}, [], True),
        ("pipx run --python ${{ env.pythonLocation }}/bin/python x", {}, [""], False),
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


@pytest.mark.parametrize(
    ("line", "kind", "found"),
    [
        # An assignment's value holds a whole `$(...)`, `$((...))` or backtick pair, so a substitution that runs into
        # the next word is read from its own `$(`.
        ("FOO=$(date) node x", "node", True),
        ("FOO=`date` node x", "node", True),
        ("n=$((n+1)) node x", "node", True),
        ("x=$(node y)", "node", True),
        ("x=$(echo node)", "node", False),
        # An octal or `\x{...}` value keeps its low eight bits, as bash 5.2 does.
        ("$'\\560ython3' x.py", "python", True),
        ("$'\\556ode' x", "node", True),
        ("$'\\x{70}ython3' x.py", "python", True),
        ("$'\\x{170}ython3' x.py", "python", True),
        ("$'node\\x{0}x' y", "node", True),
        ("$'\\x{zz}node' x", "node", False),
        # A heredoc's delimiter is the whole word, quotes taken out; quoted anywhere, its body is text.
        ("cat <<EOF-X\nhi\nEOF-X\nnode x", "node", True),
        ("cat <<END.txt\nhi\nEND.txt\nnode x", "node", True),
        ('cat <<E"OF"\nhi\nEOF\nnode x', "node", True),
        ('cat <<E"OF"\n$(node x)\nEOF', "node", False),
        ("cat <<'EOF X'\nhi\nEOF X\nnode x", "node", True),
        ("cat <<EOF-1\n$(python3 x)\nEOF-1", "python", True),
        # A heredoc or here-string given to a shell that reads its script from its input is that shell's script.
        ("bash <<'EOF'\nnode x\nEOF", "node", True),
        ("bash -s <<EOF\npython3 x\nEOF", "python", True),
        ("sudo bash -s <<'EOF'\npython3 x\nEOF", "python", True),
        ("/bin/sh <<EOF\nnode x\nEOF\necho done", "node", True),
        ("bash <<< 'node x'", "node", True),
        ('sh <<<"python3 x"', "python", True),
        ("bash <<< node", "node", True),
        ("cat <<'EOF'\nnode x\nEOF", "node", False),
        ("bash x.sh <<'EOF'\nnode x\nEOF", "node", False),
        ("bash -c 'true' <<'EOF'\nnode x\nEOF", "node", False),
        ("cat <<< 'node x'", "node", False),
        ("docker run -i img bash <<'EOF'\nnode x\nEOF", "node", False),
        ("bash <<'EOF'\necho node\nEOF", "node", False),
        # A heredoc's body inside a substitution is skipped, so its quotes do not hide what follows.
        ('msg="$(cat <<EOF\nit\'s done\nEOF\n)"\nnode x.js', "node", True),
        ('msg="$(cat <<\'EOF\'\n"quoted\nEOF\n)"\nnode x', "node", True),
        ('v="$(( 1<<2 ))"\nnode x', "node", True),
    ],
)
def test_review_forms_are_read_as_the_shell_reads_them(line, kind, found):
    assert runs_runtime(line, kind) is found


@pytest.mark.parametrize(
    ("run", "env", "ids", "flagged"),
    [
        # A substitution in an assignment's value is read from its own `$(`, with what is in front of the command.
        ("x=$(sudo pipx run y)", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("x=`sudo pipx run y`", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ('x="$(sudo pipx run y)"', {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("x=$(PIPX_DEFAULT_PYTHON= pipx run y)", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        (
            "x=$(PIPX_DEFAULT_PYTHON=/usr/bin/python3 pipx run y)",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            [],
            True,
        ),
        ("x=$(sudo bash -c 'pipx run y')", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("y=$(PIPX_DEFAULT_PYTHON=/p pipx run y)", {}, [], False),
        # A `steps` reference written another way names no id this check can read.
        ("pipx run --python ${{ steps['py'].outputs.python-path }} x", {}, ["py"], True),
        ("pipx run --python ${{ steps.py['outputs'].python-path }} x", {}, ["py"], True),
        ("pipx run --python ${{ steps[ 'py' ].outputs['python-path'] }} x", {}, ["py"], True),
        (
            "pipx run x",
            {"PIPX_DEFAULT_PYTHON": "${{ steps['py'].outputs.python-path }}"},
            ["py"],
            True,
        ),
        ("pipx run --python ${{ STEPS.py.outputs.python-path }} x", {}, ["py"], False),
        ("pipx run --python ${{ STEPS.py.outputs.python-path }} x", {}, [], True),
        # A variable no `env:` and no line of the script sets chooses nothing; `pythonLocation` is setup-python's.
        ("pipx run --python $NOPE x", {}, [], True),
        ('pipx run --python "$NOPE" x', {}, [], True),
        ("pipx run --python $HOME/py/bin/python x", {}, [], True),
        ('PIPX_DEFAULT_PYTHON="$NOPE" pipx run x', {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ('P=/opt/py/bin/python3; pipx run --python "$P" x', {}, [], False),
        ('export P=/opt/py/bin/python3\npipx run --python "$P" x', {}, [], False),
        ('for P in /a /b; do pipx run --python "$P" x; done', {}, [], False),
        ('read -r P < p.txt; pipx run --python "$P" x', {}, [], False),
        ('pipx run --python "$pythonLocation/bin/python" x', {}, [], True),
        ('pipx run --python "${pythonLocation}/bin/python" x', {}, [], True),
        ('pipx run --python "$pythonLocation/bin/python" x', {}, [""], False),
        ('pipx run --python "${pythonLocation}/bin/python" x', {}, ["py"], False),
        ("pipx run --python /usr/bin//python3 x", {}, [], True),
        # A heredoc or here-string given to a shell carries the settings in front of that shell.
        ("PIPX_DEFAULT_PYTHON=/p bash <<'EOF'\npipx run x\nEOF", {}, [], False),
        ("bash <<'EOF'\npipx run x\nEOF", {}, [], True),
        ("sudo bash <<< 'pipx run x'", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("sudo -E bash <<< 'pipx run x'", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], False),
    ],
)
def test_review_pipx_forms(run, env, ids, flagged):
    assert pipx_without_python(run, env, set(ids)) is flagged


@pytest.mark.parametrize(
    ("setup", "step", "covered"),
    [
        # A set-up condition with no top-level `||` covers a later step whose `&&` terms include all of its own
        # (Copilot on HCW-MigrateOrchestrator_App#117).
        ("a && b", "a && b && c", True),
        ("a && b", "c && a && b", True),
        ("(a && b)", "c && (a && b)", True),
        ("a && b", "(a && b) && c", True),
        ("a && b", "a && c", False),
        ("a && b", "a && b || c", False),
        ("a && b || d", "a && b && c", False),
        ("a && env.RUN", "a && env.RUN && c", False),
        ("a && b", "!cancelled() && a && b && c", False),
        ("always() && a && b", "c && a && b", True),
    ],
)
def test_a_set_up_condition_whose_terms_are_all_in_the_later_one_covers_it(setup, step, covered):
    assert covers({"if": setup}, {"if": step}) is covered


# Values YAML reads its own way: null is empty, a block scalar is its text, and `|2-` is a block scalar too.
REVIEW_YAML = """\
on: push
env:
  PY: "3.15"
jobs:
  null-env:
    runs-on: ubuntu-26.04
    steps:
      - uses: actions/setup-python@abc
        with: { python-version: "3.15" }
      - name: Scan
        env:
          PIPX_DEFAULT_PYTHON: ~
        run: pipx run checkov -d .
  block-env:
    runs-on: ubuntu-26.04
    steps:
      - uses: actions/setup-python@abc
        with: { python-version: "3.15" }
      - name: Scan
        env:
          PIPX_DEFAULT_PYTHON: >-
            /usr/bin/python3
        run: pipx run checkov -d .
  block-env-good:
    runs-on: ubuntu-26.04
    steps:
      - uses: actions/setup-python@abc
        with: { python-version: "3.15" }
      - name: Scan
        env:
          PIPX_DEFAULT_PYTHON: |
            /opt/py/bin/python3
        run: pipx run checkov -d .
  block-run:
    runs-on: ubuntu-26.04
    steps:
      - name: Script
        run: |2-
            node x.js
      - name: Other
        run: >-2
          python3 y.py
  uv-dev:
    runs-on: ubuntu-26.04
    steps:
      - uses: astral-sh/setup-uv@abc
        with: { python-version: "3.15-dev" }
      - name: Run
        run: uv run x.py
  uv-matrix:
    runs-on: ubuntu-26.04
    strategy:
      matrix:
        py: ["3.15"]
    steps:
      - uses: astral-sh/setup-uv@abc
        with: { python-version: "${{ matrix.py }}" }
      - name: Run
        run: uv run x.py
  uv-matrix-old:
    runs-on: ubuntu-26.04
    strategy:
      matrix:
        py: ["3.15", "3.14"]
    steps:
      - uses: astral-sh/setup-uv@abc
        with: { python-version: "${{ matrix.py }}" }
      - name: Run
        run: uv run x.py
  uv-env:
    runs-on: ubuntu-26.04
    steps:
      - uses: astral-sh/setup-uv@abc
        with:
          python-version: ${{ env.PY }}
      - name: Run
        run: uv run x.py
  uv-block:
    runs-on: ubuntu-26.04
    steps:
      - uses: astral-sh/setup-uv@abc
        with:
          python-version: >-
            3.15
      - name: Run
        run: uv run x.py
"""


def test_yaml_values_are_read_as_yaml_reads_them():
    jobs = read_jobs(REVIEW_YAML)
    assert unset_steps("x.yml", jobs, {}) == [
        "x.yml > block-run > Script > node",
        "x.yml > block-run > Other > python",
        "x.yml > uv-dev > Run > python",
        "x.yml > uv-matrix-old > Run > python",
    ]
    assert pipx_problems("x.yml", jobs) == [
        "x.yml > null-env > Scan > pipx",
        "x.yml > block-env > Scan > pipx",
    ]


def test_a_long_script_reads_quickly():
    """Reading the current line must not rejoin the whole script each time (8,000 lines once took a minute)."""
    script = "echo 'a' \"b\" $((1 + 2))\n" * 8000 + "node y"
    started = time.perf_counter()
    assert runs_runtime(script, "node")
    assert not pipx_without_python(script, {})
    assert time.perf_counter() - started < 1


@pytest.mark.parametrize(
    ("line", "kind", "found"),
    [
        # A heredoc ends only at a line that is exactly its delimiter, after leading tabs for `<<-` (Copilot on
        # HCW-NetworkEyes_App#395 and HCW-HybridCloudWorks#1719).
        ("cat <<EOF\n EOF \nnode x\nEOF", "node", False),
        ("cat <<EOF\nbody\n  EOF\nnode x\nEOF", "node", False),
        ("cat <<-EOF\n\tbody\n\tEOF\nnode x", "node", True),
        ("cat <<-EOF\n\tbody\n  EOF\nnode x\nEOF", "node", False),
        ("cat <<EOF\nbody\nEOF\nnode x", "node", True),
        # A substitution in an assignment's value runs before the command after it (Copilot on
        # HCW-HybridCloudWorks#1719), and `;` ends an assignment.
        ("x=$(node v.js) true", "node", True),
        ("x=`python3 v.py` true", "python", True),
        ("FOO=1;node x", "node", True),
        ("x=$(echo node) true", "node", False),
    ],
)
def test_copilot_round_one_forms_are_read_as_the_shell_reads_them(line, kind, found):
    assert runs_runtime(line, kind) is found


@pytest.mark.parametrize(
    ("run", "env", "ids", "flagged"),
    [
        # Only a setup-python step's `python-path` output is its Python; `cache-hit` or `python-version` is not.
        ("pipx run --python ${{ steps.py.outputs.cache-hit }} x", {}, ["py"], True),
        ("pipx run --python ${{ steps.py.outputs.python-version }} x", {}, ["py"], True),
        ("pipx run x", {"PIPX_DEFAULT_PYTHON": "${{ steps.py.outputs.cache-hit }}"}, ["py"], True),
        ("pipx run --python ${{ steps.py.outputs.python-path }} x", {}, ["py"], False),
        # No variable is read inside single quotes or after `\`: the shell passes `$P` on as text.
        ("pipx run --python '$P' x", {"P": "/opt/py/bin/python3"}, [], True),
        ('pipx run --python "\\$P" x', {"P": "/opt/py/bin/python3"}, [], True),
        ("pipx run --python \\$P x", {"P": "/opt/py/bin/python3"}, [], True),
        ("PIPX_DEFAULT_PYTHON='$P' pipx run x", {"P": "/opt/py/bin/python3"}, [], True),
        ("pipx run --python $'$P' x", {"P": "/opt/py/bin/python3"}, [], True),
        ('pipx run --python "$P" x', {"P": "/opt/py/bin/python3"}, [], False),
        # A command substitution this check cannot run chooses nothing.
        ('pipx run --python "$(printf /usr/bin/python3)" x', {}, [], True),
        ("pipx run --python `printf /usr/bin/python3` x", {}, [], True),
        ("PIPX_DEFAULT_PYTHON=$(command -v python3) pipx run x", {}, [], True),
        ('pipx run --python "$(command -v python3)" x', {}, [], True),
        # A wrapper's option values are read without their quotes.
        (
            "env --unset='PIPX_DEFAULT_PYTHON' pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            [],
            True,
        ),
        ("env -u 'PIPX_DEFAULT_PYTHON' pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ('env -u "PIPX_DEFAULT_PYTHON" pipx run x', {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("env -u'PIPX_DEFAULT_PYTHON' pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("env -u $'PIPX_DEFAULT_PYTHON' pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        (
            "sudo --preserve-env='PIPX_DEFAULT_PYTHON' pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            [],
            False,
        ),
        (
            'sudo --preserve-env="PATH,PIPX_DEFAULT_PYTHON" pipx run x',
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            [],
            False,
        ),
        # A name the script sets counts only where the shell sets it, and only for the commands after it.
        ('echo P=/opt/py/bin/python3; pipx run --python "$P" x', {}, [], True),
        ("echo 'P=x'; pipx run --python \"$P\" x", {}, [], True),
        ('# P=/x\npipx run --python "$P" x', {}, [], True),
        ("cat <<'EOF'\nP=/opt/py/bin/python3\nEOF\npipx run --python \"$P\" x", {}, [], True),
        ('P=/opt/py/bin/python3 pipx run --python "$P" x', {}, [], True),
        ('pipx run --python "$P" x; P=/opt/py/bin/python3', {}, [], True),
        ('pipx run --python "$P" x\nP=/opt/py/bin/python3', {}, [], True),
        ('P=/opt/py/bin/python3; pipx run --python "$P" x', {}, [], False),
        ('if true; then P=/opt/py/bin/python3; fi\npipx run --python "$P" x', {}, [], False),
        ('declare -x P=/opt/py/bin/python3\npipx run --python "$P" x', {}, [], False),
        # A `pipx` inside an assignment's `$(...)` is read even when a later command shares the line.
        ("x=$(sudo pipx run y) true", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        (
            "x=$(sudo pipx run y) PIPX_DEFAULT_PYTHON=/p pipx run z",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            [],
            True,
        ),
        ("x=$(PIPX_DEFAULT_PYTHON=/p pipx run y) PIPX_DEFAULT_PYTHON=/p pipx run z", {}, [], False),
        # The Azure CLI's Python on the runner is the runner's own too.
        ("pipx run --python /opt/az/bin/python3 x", {}, [], True),
        ("pipx run --python /opt/az/bin/python3.13 x", {}, [], True),
        ("PIPX_DEFAULT_PYTHON=/opt/az/bin/python3 pipx run x", {}, [], True),
    ],
)
def test_copilot_round_one_pipx_forms(run, env, ids, flagged):
    assert pipx_without_python(run, env, set(ids)) is flagged


@pytest.mark.parametrize(
    ("version", "kind", "below"),
    [
        # `N.M.x` names a line, like `N.M` (Copilot on HCW-HybridCloudWorks#1719).
        ("3.15.x", "python", False),
        ("3.14.x", "python", True),
        ("26.11.x", "node", False),
        ("26.10.x", "node", True),
        ("3.15.x.1", "python", None),
    ],
)
def test_a_minor_line_written_with_x_is_read_as_its_line(version, kind, below):
    assert _below_floor(version, kind) is below


# A `run: >` script is folded as YAML folds it: lines at the base indent join with a space; a blank line or a line
# indented further keeps its line break, and the base indent is the indentation indicator's when there is one (`>2-`:
# the key's indent plus two; Copilot on HCW-NetworkEyes_App#395).
FOLDED_YAML = """\
on: push
jobs:
  folded:
    runs-on: ubuntu-26.04
    steps:
      - name: Joined
        run: >-
          echo
          node x.js
      - name: Blank line
        run: >
          echo start

          node x.js
      - name: Indented
        run: >
          echo start
            python3 y.py
      - name: Indicator
        run: >2-
            echo
            pytest
"""


def test_a_folded_run_script_is_read_as_github_reads_it():
    assert unset_steps("x.yml", read_jobs(FOLDED_YAML), {}) == [
        "x.yml > folded > Blank line > node",
        "x.yml > folded > Indented > python",
        "x.yml > folded > Indicator > python",
    ]


# A composite action whose set-up step's version comes from its inputs, or is not given, cannot be read, so the floor
# test reports it (Copilot on HCW-HybridCloudWorks#1719).
INPUTS_ACTION = """\
name: sample
runs:
  using: composite
  steps:
    - uses: actions/setup-python@abc
      with:
        python-version: ${{ inputs.python }}
    - uses: actions/setup-node@abc
    - uses: astral-sh/setup-uv@abc
      with:
        python-version: ${{ inputs.python }}
    - name: Script
      shell: bash
      run: python3 x.py
"""


def test_a_composite_set_up_step_whose_version_cannot_be_read_is_reported():
    label = ".github/actions/a/action.yml"
    jobs = read_action(INPUTS_ACTION)
    assert unset_steps(label, jobs, {}) == []
    assert floor_problems(label, jobs) == [
        f"{label} > composite > step 1 > python: cannot work out the version it asks for",
        f"{label} > composite > step 2 > node: cannot work out the version it asks for",
        f"{label} > composite > step 3 > python: cannot work out the version it asks for",
    ]


@pytest.mark.parametrize(
    ("run", "env", "ids", "flagged"),
    [
        # A name the script sets stays in the shell that set it: a `-c` script, a shell fed a heredoc, a `$(...)`,
        # a backtick pair or a `( ... )` subshell hands nothing back; a child shell sees only exported names, a
        # subshell sees them all (Copilot on HCW-HybridCloudWorks#1719).
        ("bash -c 'P=/opt/py/bin/python3' ; pipx run --python \"$P\" x", {}, [], True),
        ('x=$(P=/opt/py/bin/python3; echo) ; pipx run --python "$P" x', {}, [], True),
        ('(P=/opt/py/bin/python3); pipx run --python "$P" x', {}, [], True),
        ("P=/opt/py/bin/python3; bash -c 'pipx run --python \"$P\" x'", {}, [], True),
        ("export P=/opt/py/bin/python3; bash -c 'pipx run --python \"$P\" x'", {}, [], False),
        ('P=/opt/py/bin/python3; x=$(pipx run --python "$P" x)', {}, [], False),
        ('P=/opt/py/bin/python3; (pipx run --python "$P" x)', {}, [], False),
        ("bash -c 'pipx run --python \"$P\" x'", {"P": "/opt/py/bin/python3"}, [], False),
        ("bash -c 'P=/opt/py/bin/python3; pipx run --python \"$P\" x'", {}, [], False),
        ("bash <<'EOF'\nP=/opt/py/bin/python3\nEOF\npipx run --python \"$P\" x", {}, [], True),
        ("P=/opt/py/bin/python3\nbash <<'EOF'\npipx run --python \"$P\" x\nEOF", {}, [], True),
        (
            "declare -x P=/opt/py/bin/python3\nbash <<'EOF'\npipx run --python \"$P\" x\nEOF",
            {},
            [],
            False,
        ),
        ('echo "$(P=/opt/py/bin/python3; echo)"; pipx run --python "$P" x', {}, [], True),
        ('x=`P=/opt/py/bin/python3; echo`; pipx run --python "$P" x', {}, [], True),
        ('{ P=/opt/py/bin/python3; }; pipx run --python "$P" x', {}, [], False),
        # A later assignment in the script wins over the step's, job's or workflow's `env:`, and its value is read
        # the same way (Copilot on HCW-NetworkEyes_App#395).
        ('P=/usr/bin/python3; pipx run --python "$P" x', {"P": "/opt/py/bin/python3"}, [], True),
        (
            "bash -c 'P=/usr/bin/python3'; pipx run --python \"$P\" x",
            {"P": "/opt/py/bin/python3"},
            [],
            False,
        ),
        ('pipx run --python "$P" x; P=/usr/bin/python3', {"P": "/opt/py/bin/python3"}, [], False),
        (
            "P=/usr/bin/python3\nbash -c 'pipx run --python \"$P\" x'",
            {"P": "/opt/py/bin/python3"},
            [],
            True,
        ),
        ('P=\nPIPX_DEFAULT_PYTHON="$P" pipx run x', {"P": "/opt/py/bin/python3"}, [], True),
        ('P=/opt/py/bin/python3; pipx run --python "$P" x', {"P": "/usr/bin/python3"}, [], False),
        ('P=$(command -v python3); pipx run --python "$P" x', {}, [], True),
    ],
)
def test_copilot_round_two_names_stay_in_their_shell_and_override_env(run, env, ids, flagged):
    assert pipx_without_python(run, env, set(ids)) is flagged


@pytest.mark.parametrize(
    ("run", "env", "ids", "flagged"),
    [
        # A process substitution given as pipx's Python is `/dev/fd/N` to pipx, which this check cannot vouch for
        # (Copilot on HCW-NetworkEyes_App#395).
        ("pipx run --python <(printf /opt/py/bin/python3) x", {}, [], True),
        ("PIPX_DEFAULT_PYTHON=<(printf /opt/py/bin/python3) pipx run x", {}, [], True),
        ('P=<(printf /opt/py/bin/python3); pipx run --python "$P" x', {}, [], True),
        ("pipx run --python >(cat) x", {}, [], True),
    ],
)
def test_copilot_round_three_pipx_forms(run, env, ids, flagged):
    assert pipx_without_python(run, env, set(ids)) is flagged


def test_a_process_substitution_in_an_assignment_runs_before_the_command():
    assert runs_runtime("FOO=<(node v.js) true", "node")
    assert runs_runtime("FOO=<(x) node y", "node")


# Each job names a version file; only `.python-version`, `.nvmrc` or `.node-version` at a relative path inside the
# checkout, with no `..` and no symbolic link on the way, is read (Copilot on HCW-HybridCloudWorks#1719).
VERSION_FILE_YAML = """\
on: push
jobs:
  plain:
    runs-on: ubuntu-26.04
    steps:
      - uses: actions/setup-python@abc
        with: { python-version-file: .python-version }
  nested-old:
    runs-on: ubuntu-26.04
    steps:
      - uses: actions/setup-python@abc
        with: { python-version-file: ./sub/.python-version }
  other-name:
    runs-on: ubuntu-26.04
    steps:
      - uses: actions/setup-node@abc
        with: { node-version-file: ci/node-runtime.txt }
  escape:
    runs-on: ubuntu-26.04
    steps:
      - uses: actions/setup-python@abc
        with: { python-version-file: ../../../../proc/self/.python-version }
  absolute:
    runs-on: ubuntu-26.04
    steps:
      - uses: actions/setup-python@abc
        with: { python-version-file: /etc/.python-version }
  link:
    runs-on: ubuntu-26.04
    steps:
      - uses: actions/setup-node@abc
        with: { node-version-file: .nvmrc }
  linked-folder:
    runs-on: ubuntu-26.04
    steps:
      - uses: actions/setup-python@abc
        with: { python-version-file: linked/.python-version }
  missing:
    runs-on: ubuntu-26.04
    steps:
      - uses: actions/setup-node@abc
        with: { node-version-file: .node-version }
"""


def test_a_version_file_is_read_only_inside_the_checkout_and_by_its_usual_name(tmp_path):
    root = tmp_path / "repo"
    (root / "sub").mkdir(parents=True)
    (root / "ci").mkdir()
    (root / "real").mkdir()
    (root / ".python-version").write_text("3.15\n", encoding="utf-8")
    (root / "sub" / ".python-version").write_text("3.14\n", encoding="utf-8")
    (root / "ci" / "node-runtime.txt").write_text("26\n", encoding="utf-8")
    (root / "real" / ".nvmrc").write_text("26\n", encoding="utf-8")
    (root / "real" / ".python-version").write_text("3.15\n", encoding="utf-8")
    (root / ".nvmrc").symlink_to(root / "real" / ".nvmrc")
    (root / "linked").symlink_to(root / "real", target_is_directory=True)
    label = "x.yml"
    assert floor_problems(label, read_jobs(VERSION_FILE_YAML), root) == [
        f"{label} > nested-old > step 1 > python: asks for 3.14, below the floor",
        f"{label} > other-name > step 1 > node: cannot work out the version it asks for",
        f"{label} > escape > step 1 > python: cannot work out the version it asks for",
        f"{label} > absolute > step 1 > python: cannot work out the version it asks for",
        f"{label} > link > step 1 > node: cannot work out the version it asks for",
        f"{label} > linked-folder > step 1 > python: cannot work out the version it asks for",
        f"{label} > missing > step 1 > node: cannot work out the version it asks for",
    ]


def test_a_composite_action_without_steps_stops_the_test():
    """It would otherwise read as having no steps (Copilot on HCW-HybridCloudWorks#1719)."""
    with pytest.raises(AssertionError, match="no runs: steps: list"):
        read_action("name: x\nruns:\n  using: composite\n")


@pytest.mark.parametrize(
    ("run", "env", "ids", "flagged"),
    [
        # A: a GitHub expression other than setup-python's `python-path` output or `env.pythonLocation` chooses
        # nothing (Copilot on HCW-NetworkEyes_AddOn#109, HCW-MigrateOrchestrator_AddOn#75 and
        # HCW-CloudCrawler_App#85).
        ("pipx run --python ${{ github.workspace }}/.venv/bin/python x", {}, ["py"], True),
        ("pipx run --python ${{ inputs.python }} x", {}, ["py"], True),
        ("pipx run --python ${{ env.UNSET }} x", {}, ["py"], True),
        ("pipx run x", {"PIPX_DEFAULT_PYTHON": "${{ inputs.python }}"}, ["py"], True),
        ("pipx run x", {"PIPX_DEFAULT_PYTHON": "${{ env.NOT_PYTHON_LOCATION }}"}, ["py"], True),
        ('pipx run --python "$P" x', {"P": "${{ github.workspace }}/py"}, ["py"], True),
        (
            "pipx run --python ${{ steps.py.outputs.python-path }}${{ github.sha }} x",
            {},
            ["py"],
            True,
        ),
        ("pipx run --python steps.py.outputs.python-path x", {}, ["py"], True),
        # `${{ env.X }}` is read as GitHub replaces it: it chooses when the value it stands for does.
        (
            "pipx run --python ${{ env.PY }} x",
            {"PY": "${{ steps.py.outputs.python-path }}"},
            ["py"],
            False,
        ),
        (
            "pipx run --python ${{ env.PY }} x",
            {"PY": "${{ steps.py.outputs.python-path }}"},
            [],
            True,
        ),
        ("pipx run --python ${{ env.PY }} x", {"PY": "/usr/bin/python3"}, ["py"], True),
        ("pipx run --python ${{ env.PY }} x", {"PY": "/opt/py/bin/python3"}, [], False),
        ("pipx run --python ${{env.PY}} x", {"PY": "${{ env.PY }}"}, ["py"], True),
        # `env` here is the context GitHub has already evaluated (see `step_env`), so a value in it that still holds
        # `${{ env.PY }}` was a sibling GitHub does not read, and chooses nothing (round 3, HCW-HybridCloudWorks#1707).
        (
            "pipx run x",
            {"PIPX_DEFAULT_PYTHON": "${{ env.PY }}", "PY": "/opt/py/bin/python3"},
            [],
            True,
        ),
        (
            'pipx run --python "$PYTHON_PATH" x',
            {"PYTHON_PATH": "${{ steps.python.outputs.python-path }}"},
            ["python"],
            False,
        ),
        ("PY=/opt/py; pipx run --python ${{ env.PY }} x", {"PY": "/usr/bin/python3"}, [], True),
        # B: `$pythonLocation` and `${{ env.pythonLocation }}` count only after a set-up step, with or without an id.
        ("pipx run --python ${{ env.pythonLocation }}/bin/python3 x", {}, ["py"], False),
        ("pipx run x", {"PIPX_DEFAULT_PYTHON": "${{ env.pythonLocation }}/bin/python3"}, [], True),
        (
            "pipx run x",
            {"PIPX_DEFAULT_PYTHON": "${{ env.pythonLocation }}/bin/python3"},
            [""],
            False,
        ),
        ("PIPX_DEFAULT_PYTHON=$pythonLocation/bin/python3 pipx run x", {}, [], True),
        ("PIPX_DEFAULT_PYTHON=$pythonLocation/bin/python3 pipx run x", {}, [""], False),
        # An `env:` that sets `pythonLocation` itself leaves it unknown which value GitHub uses (round 3,
        # HCW-HybridCloudWorks#1707).
        (
            "pipx run --python ${{ env.pythonLocation }}/bin/python3 x",
            {"pythonLocation": "/opt/py"},
            [],
            True,
        ),
        (
            "pipx run --python ${{ env.pythonLocation }}/bin/python3 x",
            {"pythonLocation": "/usr"},
            [""],
            True,
        ),
        # C: a path is compared as the shell resolves it (Copilot on HCW-MigrateOrchestrator_AddOn#75).
        ("pipx run --python /usr/bin/../bin/python3 x", {}, [], True),
        ("pipx run --python /usr/./bin/python3 x", {}, [], True),
        ("pipx run --python //usr/bin/python3 x", {}, [], True),
        ("pipx run --python /opt/az/lib/../bin/python3 x", {}, [], True),
        ("pipx run --python /usr/bin/python3/ x", {}, [], True),
        ("PIPX_DEFAULT_PYTHON=/usr/local/../bin/python3 pipx run x", {}, [], True),
        ("pipx run x", {"PIPX_DEFAULT_PYTHON": "/bin/./python3"}, [], True),
        # /usr/local/bin is the runner's too since round 3 (HCW-HybridCloudWorks#1707), so this path is the runner's.
        ("pipx run --python /usr/bin/../local/bin/python3 x", {}, [], True),
        ("pipx run --python /usr/bin/../../opt/py/bin/python3 x", {}, [], False),
        ("pipx run --python /opt/py/../py/bin/python3 x", {}, [], False),
    ],
)
def test_copilot_round_four_pipx_values(run, env, ids, flagged):
    assert pipx_without_python(run, env, set(ids)) is flagged


def test_a_matrix_value_given_to_pipx_is_read_for_every_entry():
    """`${{ matrix.X }}` is read as GitHub replaces it, once for each entry of the job's matrix list
    (Copilot on HCW-NetworkEyes_AddOn#109): one entry naming the runner's Python is enough to report it."""
    run = "pipx run --python ${{ matrix.py }} x"
    assert (
        pipx_without_python(run, {}, set(), {"py": ["/opt/a/python3", "/opt/b/python3"]}) is False
    )
    assert (
        pipx_without_python(run, {}, set(), {"py": ["/opt/a/python3", "/usr/bin/python3"]}) is True
    )
    assert pipx_without_python(run, {}, set(), {}) is True
    env = {"PIPX_DEFAULT_PYTHON": "${{ matrix.py }}"}
    assert pipx_without_python("pipx run x", env, set(), {"py": ["/opt/a/python3"]}) is False
    jobs = read_jobs(
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix:\n        py: [/opt/a/python3, "
        "/bin/python3]\n    steps:\n      - name: Scan\n        run: pipx run --python ${{ matrix.py }} x\n"
    )
    assert pipx_problems("x.yml", jobs) == ["x.yml > j > Scan > pipx"]


def test_a_python_location_counts_only_after_an_id_less_set_up_step_too():
    """`python_setup_ids` names a set-up step without an id as `""` (Copilot on HCW-NetworkEyes_AddOn#109)."""
    jobs = read_jobs(
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - name: Before\n"
        '        run: pipx run --python "$pythonLocation/bin/python3" x\n'
        "      - uses: actions/setup-python@abc\n        with:\n          python-version: '3.15'\n"
        "      - name: After\n"
        '        run: pipx run --python "$pythonLocation/bin/python3" x\n'
        "      - name: Skipped set-up\n        if: inputs.go\n        uses: actions/setup-python@abc\n"
    )
    assert python_setup_ids(jobs["j"]["steps"], 2) == {""}
    assert pipx_problems("x.yml", jobs) == ["x.yml > j > Before > pipx"]


@pytest.mark.parametrize(
    ("setup", "step", "covered"),
    [
        # D: a set-up `&&` term that joins terms with `||` holds when one of those is among the later step's `&&`
        # terms (Copilot on HCW-MigrateOrchestrator_App#118).
        ("(a || b) && c", "a && c", True),
        ("(a || b) && c", "c && b", True),
        ("(a || b) && c", "d && c", False),
        ("(a || b) && c", "a", False),
        ("(a || b) && c", "(a || b) && c && d", True),
        ("(a || env.B) && c", "a && c", True),
        ("(env.A || b) && c", "env.A && c", False),
        ("(a || b) && c", "a && c || d", False),
        ("a || b && c", "a && c", True),
        ("(a || (b && d)) && c", "b && d && c", False),
    ],
)
def test_a_set_up_term_joined_with_or_holds_when_one_of_its_terms_does(setup, step, covered):
    assert covers({"if": setup}, {"if": step}) is covered


BLOCK_VALUE_YAML = """jobs:
  j:
    runs-on: ubuntu-26.04
    steps:
      - id: py
        uses: actions/setup-python@abc
        with:
          python-version: '3.15'
      - name: Comment after block
        env:
          PIPX_DEFAULT_PYTHON: |-
            /usr/bin/python3
# a comment at column 0
        run: pipx run x
      - name: Indented comment after block
        env:
          PIPX_DEFAULT_PYTHON: |-
            /usr/bin/python3
          # a comment at the key's indent
        run: pipx run x
      - name: Key after block
        env:
          A: |-
            /usr/bin/python3
          PIPX_DEFAULT_PYTHON: ${{ steps.py.outputs.python-path }}
        run: pipx run x
      - name: Blank and comment lines inside
        env:
          A: |
            a

            # kept: indented like the value
            b
        run: echo "$A"
"""


def test_a_block_value_ends_at_the_first_line_indented_no_further_than_its_key():
    """A comment after a block value in `env:` or `with:`, indented no further than the value's key,
    ends the value, as YAML reads it, instead of being read into it (found while porting the check to
    HCW-MigrateOrchestrator); blank lines and comment-like lines indented like the value stay in it."""
    jobs = read_jobs(BLOCK_VALUE_YAML)
    envs = [step.get("env") for step in jobs["j"]["steps"]]
    assert envs[1:] == [
        {"PIPX_DEFAULT_PYTHON": "/usr/bin/python3"},
        {"PIPX_DEFAULT_PYTHON": "/usr/bin/python3"},
        {"A": "/usr/bin/python3", "PIPX_DEFAULT_PYTHON": "${{ steps.py.outputs.python-path }}"},
        {"A": "a\n\n# kept: indented like the value\nb\n"},
    ]
    assert pipx_problems("x.yml", jobs) == [
        "x.yml > j > Comment after block > pipx",
        "x.yml > j > Indented comment after block > pipx",
    ]


# Round 3 (https://github.com/saulpatinojr/HCW-HybridCloudWorks/issues/1707#issuecomment-6848049164): the same cases
# as the website's scripts/workflow-runtime-setup.test.mjs, in the same order.
@pytest.mark.parametrize(
    ("line", "kind", "found"),
    [
        # 2: a quoted plain word is that word to the shell, so `'node' x` runs node.
        ("'node' x.js", "node", True),
        ('"python3" x.py', "python", True),
        ("'/usr/bin/'python3 x.py", "python", True),
        ('"no""de" x', "node", True),
        ("sudo 'node' x", "node", True),
        ("echo 'node' x", "node", False),
        ("'node x'", "node", False),
        ('"no\\de" x', "node", False),
        ("'FOO=1' node x", "node", False),
        # 15: `eval` runs its arguments as a script.
        ("eval node x.js", "node", True),
        ("eval 'node x.js'", "node", True),
        ('eval "python3 x.py"', "python", True),
        ("eval -- node x", "node", True),
        ("eval echo 'a; node x'", "node", True),
        ("x=$(eval 'node y')", "node", True),
        ("echo eval node x", "node", False),
        ("eval echo node", "node", False),
        # 5: the outer shell runs only the substitutions of a double-quoted string, not the rest of its text.
        ('echo "a; node x $(true)"', "node", False),
        ('echo "a | python3 x `true`"', "python", False),
        ('echo "\\$(node x)"', "node", False),
        ('echo "<(node x)"', "node", False),
        ('bash -c "x; node y $(true)"', "node", True),
        ('echo "a $(node x) b"', "node", True),
    ],
)
def test_round_three_forms_are_read_as_the_shell_reads_them(line, kind, found):
    assert runs_runtime(line, kind) is found


@pytest.mark.parametrize(
    ("run", "env", "ids", "flagged"),
    [
        # 1: `export -n` and `declare +x` take a name's export away, so a child shell no longer sees it.
        ("export -n P=/opt/py/bin/python3; bash -c 'pipx run --python \"$P\" x'", {}, [], True),
        (
            "export P=/opt/py/bin/python3; export -n P; bash -c 'pipx run --python \"$P\" x'",
            {},
            [],
            True,
        ),
        (
            "export -n P; bash -c 'pipx run --python \"$P\" x'",
            {"P": "/opt/py/bin/python3"},
            [],
            True,
        ),
        (
            "declare +x P; bash -c 'pipx run --python \"$P\" x'",
            {"P": "/opt/py/bin/python3"},
            [],
            True,
        ),
        ('export -n P=/opt/py/bin/python3; pipx run --python "$P" x', {}, [], False),
        ("export -n PIPX_DEFAULT_PYTHON; pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("export P=/opt/py/bin/python3; bash -c 'pipx run --python \"$P\" x'", {}, [], False),
        # 10: `unset` removes a name for the rest of that shell.
        ("unset PIPX_DEFAULT_PYTHON; pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("unset -v PIPX_DEFAULT_PYTHON\npipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("unset -f PIPX_DEFAULT_PYTHON; pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], False),
        ("(unset PIPX_DEFAULT_PYTHON); pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], False),
        (
            "unset PIPX_DEFAULT_PYTHON; PIPX_DEFAULT_PYTHON=/p pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            [],
            False,
        ),
        (
            "unset PIPX_DEFAULT_PYTHON; PIPX_DEFAULT_PYTHON=/p bash -c 'pipx run x'",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            [],
            False,
        ),
        (
            "unset PIPX_DEFAULT_PYTHON; bash -c 'pipx run x'",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            [],
            True,
        ),
        (
            "bash -c 'unset PIPX_DEFAULT_PYTHON; pipx run x'",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            [],
            True,
        ),
        (
            "bash -c 'unset PIPX_DEFAULT_PYTHON'; pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            [],
            False,
        ),
        ('unset P; pipx run --python "$P" x', {"P": "/opt/py/bin/python3"}, [], True),
        (
            "PIPX_DEFAULT_PYTHON=/usr/bin/python3; pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            [],
            True,
        ),
        # An export in the script that chooses is read too since Copilot's third review of HCW-NetworkEyes_App#399.
        ("export PIPX_DEFAULT_PYTHON=/opt/py/bin/python3; pipx run x", {}, [], False),
        # 5: the outer shell runs only the substitutions of a double-quoted string, not the rest of its text.
        ('PIPX_DEFAULT_PYTHON=/p bash -c "x; pipx run y $(true)"', {}, [], False),
        ('bash -c "x; pipx run y $(true)"', {}, [], True),
        ('echo "a; pipx run y $(true)"', {}, [], False),
        ('PIPX_DEFAULT_PYTHON=/p bash -c "echo $(pipx run y)"', {}, [], True),
        # 2: a quoted plain word is that word to the shell, so `'node' x` runs node.
        ("'pipx' run x", {}, [], True),
        ('"pipx" run --python /p x', {}, [], False),
        # 15: `eval` runs its arguments as a script.
        ("eval 'pipx run x'", {}, [], True),
        ("eval pipx run x", {}, [], True),
        ("PIPX_DEFAULT_PYTHON=/p eval 'pipx run x'", {}, [], False),
        # 9: `sudo -i` resets the environment whatever `-E` says; a list naming the variable still passes it.
        ("sudo -iE pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("sudo -E -i pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("sudo --login --preserve-env pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        ("sudo --log -E pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        (
            "sudo -i --preserve-env=PIPX_DEFAULT_PYTHON pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            [],
            False,
        ),
        ("sudo -E pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], False),
        # 12: a bare name is looked up on PATH, so only the floor's own `python3.15` counts.
        ("pipx run --python python3 x", {}, [], True),
        ("pipx run --python python x", {}, [], True),
        ("pipx run --python python3.14 x", {}, [], True),
        ("pipx run --python 3.15 x", {}, [], True),
        ("pipx run --python python3.15 x", {}, [], False),
        ("pipx run x", {"PIPX_DEFAULT_PYTHON": "python3"}, [], True),
        ("PIPX_DEFAULT_PYTHON=python3.15 pipx run x", {}, [], False),
        ('P=python3; pipx run --python "$P" x', {}, [], True),
        # 13: a `..` after a part this check cannot see can climb anywhere.
        ("pipx run --python ${{ env.pythonLocation }}/../../usr/bin/python3 x", {}, [""], True),
        ("pipx run --python ${{ steps.py.outputs.python-path }}/../python3 x", {}, ["py"], True),
        ('pipx run --python "$pythonLocation/../../../usr/bin/python3" x', {}, [""], True),
        ('pipx run --python "$P/../bin/python3" x', {"P": "/opt/py/bin"}, [], False),
        ("pipx run --python ${{ env.pythonLocation }}/bin/python3 x", {}, [""], False),
        # 14: `${{ env.pythonLocation }}` stays setup-python's word; an `env:` that sets it leaves it unknown.
        (
            "pipx run --python ${{ env.pythonLocation }}/bin/python3 x",
            {"pythonLocation": "/opt/py"},
            [""],
            True,
        ),
        (
            'pipx run --python "$pythonLocation/bin/python3" x',
            {"pythonLocation": "/opt/py"},
            [""],
            True,
        ),
        (
            "pipx run x",
            {
                "PIPX_DEFAULT_PYTHON": "${{ env.pythonLocation }}/bin/python3",
                "pythonLocation": "/usr",
            },
            [""],
            True,
        ),
        (
            "pipx run x",
            {"PIPX_DEFAULT_PYTHON": "${{ env.pythonLocation }}/bin/python3"},
            [""],
            False,
        ),
        # 16: globs, braces, escapes and a leading `~` are read before the shell could expand them.
        ("pipx run --python /usr/bin/python* x", {}, [], True),
        ("pipx run --python /usr/bin/pyt\\hon3 x", {}, [], True),
        ("pipx run --python ~/py/bin/python3 x", {}, [], True),
        ("pipx run --python /opt/py/bin/python{3,} x", {}, [], True),
        ("pipx run --python /usr/bin/python3.1? x", {}, [], True),
        ("PIPX_DEFAULT_PYTHON=~/py/bin/python3 pipx run x", {}, [], True),
        ("pipx run --python /opt/py/bin/pyth\\on3 x", {}, [], False),
        # 8: /usr/local/bin is the runner's.
        ("pipx run --python /usr/local/bin/python3 x", {}, [], True),
        ("PIPX_DEFAULT_PYTHON=/usr/local/bin/python3.15 pipx run x", {}, [], True),
        ("pipx run x", {"PIPX_DEFAULT_PYTHON": "/usr/local/bin/python3"}, [], True),
    ],
)
def test_round_three_pipx_forms(run, env, ids, flagged):
    assert pipx_without_python(run, env, set(ids)) is flagged


# 3: sudo looks its command up on its own secure_path, so it runs the runner's runtime even after a set-up step.
ROUND_THREE_SUDO_YAML = 'on: push\njobs:\n  sudo-python:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: sudo python3 x.py\n  sudo-e-node:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-node@abc\n        with: { node-version: "26" }\n      - name: Run\n        run: sudo -E node x.js\n  sudo-path:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: sudo env "PATH=$PATH" python3 x.py\n  sudo-shell:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-node@abc\n        with: { node-version: "26" }\n      - name: Run\n        run: sudo bash -c \'node x.js\'\n  sudo-own-path:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: sudo PATH="$PATH" python3 x.py\n  sudo-env-path-shell:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: sudo env PATH="$PATH" bash -c \'python3 x.py\'\n  sudo-heredoc:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: |\n          sudo bash <<\'EOF\'\n          python3 x.py\n          EOF\n  sudo-split:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: sudo -u nobody env -S \'python3 x.py\'\n  no-sudo:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: python3 x.py\n'


def test_round_three_sudo_workflow():
    jobs = read_jobs(ROUND_THREE_SUDO_YAML)
    assert unset_steps("x.yml", jobs, {}) == [
        "x.yml > sudo-python > Run > python",
        "x.yml > sudo-e-node > Run > node",
        "x.yml > sudo-shell > Run > node",
        "x.yml > sudo-own-path > Run > python",
        "x.yml > sudo-heredoc > Run > python",
        "x.yml > sudo-split > Run > python",
    ]
    assert pipx_problems("x.yml", jobs) == []


# 4: a step's `shell:` (or `defaults.run.shell`) runs its text with that program.
ROUND_THREE_SHELL_YAML = 'on: push\ndefaults:\n  run:\n    shell: bash\njobs:\n  python-shell:\n    runs-on: ubuntu-26.04\n    steps:\n      - name: Script\n        shell: python\n        run: print(1)\n  python-shell-set-up:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Script\n        shell: python\n        run: print(1)\n  node-shell:\n    runs-on: ubuntu-26.04\n    steps:\n      - name: Script\n        shell: node {0}\n        run: console.log(1)\n  job-default:\n    runs-on: ubuntu-26.04\n    defaults:\n      run:\n        shell: python3 {0}\n    steps:\n      - name: Script\n        run: print(1)\n  pwsh:\n    runs-on: ubuntu-26.04\n    steps:\n      - name: Script\n        shell: pwsh\n        run: Write-Output 1\n  sudo-shell:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Script\n        shell: sudo python3 {0}\n        run: print(1)\n  uses-only:\n    runs-on: ubuntu-26.04\n    steps:\n      - name: Action\n        shell: python\n        uses: actions/checkout@abc\n'


def test_round_three_shell_workflow():
    jobs = read_jobs(ROUND_THREE_SHELL_YAML)
    assert unset_steps("x.yml", jobs, {}) == [
        "x.yml > python-shell > Script > python",
        "x.yml > node-shell > Script > node",
        "x.yml > job-default > Script > python",
        "x.yml > sudo-shell > Script > python",
    ]
    assert pipx_problems("x.yml", jobs) == []


# 4: a step's `shell:` (or `defaults.run.shell`) runs its text with that program.
ROUND_THREE_SHELL_WORKFLOW_DEFAULT_YAML = "on: push\ndefaults:\n  run:\n    shell: python\njobs:\n  inherits:\n    runs-on: ubuntu-26.04\n    steps:\n      - name: Script\n        run: print(1)\n  own-default:\n    runs-on: ubuntu-26.04\n    defaults:\n      run:\n        shell: bash\n    steps:\n      - name: Script\n        run: print(1)\n"


def test_round_three_shell_workflow_default_workflow():
    jobs = read_jobs(ROUND_THREE_SHELL_WORKFLOW_DEFAULT_YAML)
    assert unset_steps("x.yml", jobs, {}) == ["x.yml > inherits > Script > python"]
    assert pipx_problems("x.yml", jobs) == []


# 7: `env` is evaluated level by level, as GitHub does.
ROUND_THREE_ENV_LEVELS_YAML = 'on: push\nenv:\n  PY: /opt/py/bin/python3\n  V: "3.15"\njobs:\n  job-level:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        env:\n          PIPX_DEFAULT_PYTHON: ${{ env.PY }}\n        run: pipx run x\n  sibling:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        env:\n          OWN: /opt/py/bin/python3\n          PIPX_DEFAULT_PYTHON: ${{ env.OWN }}\n        run: pipx run x\n  job-env-reads-env:\n    runs-on: ubuntu-26.04\n    env:\n      A: ${{ env.PY }}\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        run: pipx run --python ${{ env.A }} x\n  one-round:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        env:\n          B: ${{ env.PY }}\n        run: pipx run --python ${{ env.B }} x\n  uv-step-env:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: astral-sh/setup-uv@abc\n        env:\n          W: ${{ env.V }}\n        with:\n          python-version: ${{ env.W }}\n      - name: Run\n        run: uv run x.py\n  uv-job-env:\n    runs-on: ubuntu-26.04\n    env:\n      W: ${{ env.V }}\n    steps:\n      - uses: astral-sh/setup-uv@abc\n        with:\n          python-version: ${{ env.W }}\n      - name: Run\n        run: uv run x.py\n  location:\n    runs-on: ubuntu-26.04\n    env:\n      pythonLocation: /opt/py\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        run: pipx run --python ${{ env.pythonLocation }}/bin/python3 x\n  location-shell:\n    runs-on: ubuntu-26.04\n    env:\n      pythonLocation: /opt/py\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        run: pipx run --python "$pythonLocation/bin/python3" x\n  location-set-up:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        run: pipx run --python ${{ env.pythonLocation }}/bin/python3 x\n'


def test_round_three_env_levels_workflow():
    jobs = read_jobs(ROUND_THREE_ENV_LEVELS_YAML)
    assert unset_steps("x.yml", jobs, {}) == ["x.yml > uv-job-env > Run > python"]
    assert pipx_problems("x.yml", jobs) == [
        "x.yml > sibling > Scan > pipx",
        "x.yml > job-env-reads-env > Scan > pipx",
        "x.yml > location > Scan > pipx",
        "x.yml > location-shell > Scan > pipx",
    ]


# 17: values are read as YAML reads them (items 6, 11, 17 and 18).
ROUND_THREE_YAML_VALUES_YAML = 'on: push\njobs:\n  comment-in-env:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        env:\n          PIPX_DEFAULT_PYTHON: |-\n            /opt/py/bin/python3\n           # a comment indented between the key and the value\n        run: pipx run x\n  comment-in-with:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: astral-sh/setup-uv@abc\n        with:\n          python-version: |-\n            3.15\n           # a comment indented between the key and the value\n      - name: Run\n        run: uv run x.py\n  comment-in-run:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        env:\n          PIPX_DEFAULT_PYTHON: /opt/py/bin/python3\n        run: |\n            pipx run x\n          # a comment indented between the key and the script\n  double-quoted:\n    runs-on: ubuntu-26.04\n    steps:\n      - name: Run\n        run: "python3 x.py" # a comment\n  escapes:\n    runs-on: ubuntu-26.04\n    steps:\n      - name: Run\n        run: "\\x70ython3 x.py"\n      - name: Tab\n        run: "node\\tx.js"\n  single-quoted:\n    runs-on: ubuntu-26.04\n    steps:\n      - name: Run\n        run: \'echo \'\'; node x\'\'\'\n  matrix-comment:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix:\n        py:\n          - /usr/bin/python3 # the runner\'s\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        env:\n          PIPX_DEFAULT_PYTHON: ${{ matrix.py }}\n        run: pipx run x\n  matrix-quoted:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix:\n        py:\n          - "3.15" # the floor\n    steps:\n      - uses: astral-sh/setup-uv@abc\n        with:\n          python-version: ${{ matrix.py }}\n      - name: Run\n        run: uv run x.py\n  number:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: astral-sh/setup-uv@abc\n        with:\n          python-version: 3.20\n      - name: Run\n        run: uv run x.py\n  number-matrix:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix:\n        py: [3.20]\n    steps:\n      - uses: astral-sh/setup-uv@abc\n        with:\n          python-version: ${{ matrix.py }}\n      - name: Run\n        run: uv run x.py\n'


def test_round_three_yaml_values_workflow():
    jobs = read_jobs(ROUND_THREE_YAML_VALUES_YAML)
    assert unset_steps("x.yml", jobs, {}) == [
        "x.yml > double-quoted > Run > python",
        "x.yml > escapes > Tab > node",
        "x.yml > escapes > Run > python",
        "x.yml > number > Run > python",
        "x.yml > number-matrix > Run > python",
    ]
    assert pipx_problems("x.yml", jobs) == ["x.yml > matrix-comment > Scan > pipx"]


@pytest.mark.parametrize(
    "text",
    [
        "jobs:\n  j: {runs-on: ubuntu-26.04, steps: [{run: python3 x.py}]}\n",
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps: [{run: python3 x.py}]\n",
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - {run: python3 x.py}\n",
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    strategy: {matrix: {py: [a]}}\n    steps:\n      - run: echo\n",
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix: {py: [a]}\n    steps:\n      - run: echo\n",
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - run: echo a\n          node x\n",
        'jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - run: "echo a\n          node x"\n',
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - env:\n          A: one\n            two\n        run: echo\n",
        # A matrix item continued on the next line (Copilot on HCW-NetworkEyes_App#399).
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix:\n        py:\n          - /usr/bin/python3\n            --x\n    steps:\n      - run: echo\n",
    ],
)
def test_round_three_every_reader_refuses_these_forms(text):
    """So every copy reads the same files (item 11): the website's YAML reader refuses them too."""
    with pytest.raises(AssertionError):
        read_jobs(text)


# The pre-PR review of round 3 (HCW-HybridCloudWorks#1707): the same cases as the website's
# scripts/workflow-runtime-setup.test.mjs, in the same order.
@pytest.mark.parametrize(
    ("line", "kind", "found"),
    [
        # 1: a quoted assignment given to env or sudo is still an assignment.
        ('env "PATH=$PATH" python3 x', "python", True),
        ('sudo env "PATH=$PATH" python3 x', "python", True),
        ("env 'A=1' node x", "node", True),
        ("sudo -E 'A=1' node x", "node", True),
        ('"A=1" node x', "node", False),
        ("env -S 'A=1 node x'", "node", True),
        ("echo env 'A=1' node x", "node", False),
        # 5: empty quotes, escapes, builtin and a name that ends at an operator.
        ("''node x", "node", True),
        ('""node x', "node", True),
        ('n""ode x', "node", True),
        ("\\node x", "node", True),
        ("n\\ode x", "node", True),
        ("'' node x", "node", False),
        ("'node'&& echo", "node", True),
        ("'npx'|cat", "node", True),
        ("'node';", "node", True),
        ("builtin eval node x", "node", True),
        ("\\eval node x", "node", True),
        ("python3<<EOF\nx\nEOF", "python", True),
        ("(cd a && npm)", "node", True),
        ("x=$(node)", "node", True),
        ("node;", "node", True),
        ("python3>log", "python", True),
        ('case "$k" in node) echo ;; esac', "node", False),
        ("node|npm) echo hi ;;", "node", False),
        ("node) node x ;;", "node", True),
        ("nodejs x", "node", False),
        ("echo node;", "node", False),
    ],
)
def test_round_three_review_forms_are_read_as_the_shell_reads_them(line, kind, found):
    assert runs_runtime(line, kind) is found


@pytest.mark.parametrize(
    ("line", "kind", "found"),
    [
        # 2: only the outer PATH, passed on by env after sudo, keeps the set-up runtime.
        ("sudo env PATH=$PATH python3 x", "python", False),
        ('sudo env "PATH=$PATH" python3 x', "python", False),
        ('sudo env PATH="${PATH}" python3 x', "python", False),
        ("sudo env PATH=$PATH:/usr/bin python3 x", "python", False),
        ("sudo env PATH=/usr/bin:$PATH python3 x", "python", True),
        ("sudo env PATH=/usr/bin python3 x", "python", True),
        ("sudo bash -c 'env PATH=$PATH node x'", "node", True),
        # Copilot on the round-3 ports: inside a sudo'd script `$PATH` is already sudo's `secure_path`.
        ("sudo bash -c 'sudo env PATH=$PATH node x'", "node", True),
        ("sudo bash -c 'sudo env PATH=$PATH python3 x'", "python", True),
        ("sudo bash -c 'env PATH=$PATH sudo env PATH=$PATH node x'", "node", True),
        ("sudo bash -c 'bash -c \"sudo env PATH=$PATH node x\"'", "node", True),
        ("sudo env PATH=$PATH bash -c 'sudo env PATH=$PATH node x'", "node", False),
        ("sudo env PATH=$PATH bash -c 'sudo bash -c \"sudo env PATH=$PATH node x\"'", "node", True),
        ("env PATH=$PATH sudo python3 x", "python", True),
        # Copilot's review of the round-3 ports (HCW-CloudCrawler_App#90): `env PATH=/usr/bin` looks node up on
        # /usr/bin, not on the set-up PATH.
        ("env PATH=/usr/bin node x", "node", True),
    ],
)
def test_round_three_review_sudo_passes_the_set_up_runtime_only_with_the_outer_path(
    line, kind, found
):
    assert runs_through_sudo(line, kind) is found


@pytest.mark.parametrize(
    ("run", "env", "ids", "flagged"),
    [
        # 1: a quoted assignment given to env or sudo is still an assignment.
        ('env "A=1" pipx run x', {}, [], True),
        ('env "PIPX_DEFAULT_PYTHON=/usr/bin/python3" pipx run x', {}, [], True),
        ('env "PIPX_DEFAULT_PYTHON=/opt/py/bin/python3" pipx run x', {}, [], False),
        ('sudo env "PIPX_DEFAULT_PYTHON=/opt/py/bin/python3" pipx run x', {}, [], False),
        ("env 'PIPX_DEFAULT_PYTHON=' pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, [], True),
        # 4: an unset pythonLocation is not setup-python's any more.
        ('unset pythonLocation; pipx run --python "$pythonLocation/bin/python3" x', {}, [""], True),
        (
            '(unset pythonLocation); pipx run --python "$pythonLocation/bin/python3" x',
            {},
            [""],
            False,
        ),
        ('pipx run --python "$pythonLocation/bin/python3" x', {}, [""], False),
    ],
)
def test_round_three_review_pipx_forms(run, env, ids, flagged):
    assert pipx_without_python(run, env, set(ids)) is flagged


# 1 and 7: a quoted assignment given to env does not hide the command after it, and a step whose shell is run through sudo runs its text under sudo.
ROUND_THREE_REVIEW_SUDO_YAML = 'on: push\njobs:\n  quoted-no-set-up:\n    runs-on: ubuntu-26.04\n    steps:\n      - name: Run\n        run: sudo env "PATH=$PATH" python3 x\n  env-quoted-no-set-up:\n    runs-on: ubuntu-26.04\n    steps:\n      - name: Run\n        run: env "PATH=$PATH" python3 x\n  quoted-set-up:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: sudo env "PATH=$PATH" python3 x\n  sudo-shell:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        shell: sudo bash -e {0}\n        run: python3 x\n  sudo-default-shell:\n    runs-on: ubuntu-26.04\n    defaults:\n      run:\n        shell: sudo bash -e {0}\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: python3 x\n  sudo-path-shell:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        shell: sudo env PATH="$PATH" bash -e {0}\n        run: python3 x\n'


def test_round_three_review_sudo_workflow():
    jobs = read_jobs(ROUND_THREE_REVIEW_SUDO_YAML)
    # Since round 4 (HCW-HybridCloudWorks#1707) `sudo-path-shell` is reported: its `shell:` gives env the text
    # `PATH=$PATH`, since the runner fills nothing in (see `literal_shell`), so env replaces PATH and the set-up Python
    # is not found.
    assert unset_steps("x.yml", jobs, {}) == [
        "x.yml > quoted-no-set-up > Run > python",
        "x.yml > env-quoted-no-set-up > Run > python",
        "x.yml > sudo-shell > Run > python",
        "x.yml > sudo-default-shell > Run > python",
        "x.yml > sudo-path-shell > Run > python",
    ]
    assert pipx_problems("x.yml", jobs) == []


# Copilot on the round-3 ports (HCW-HybridCloudWorks#1707): under a `shell:` run through sudo the step's `$PATH` is
# sudo's `secure_path`, so a `sudo env "PATH=$PATH"` in its text passes that on, not the set-up Python. The `path-shell`
# job is reported too since round 4 (HCW-HybridCloudWorks#1707): the runner starts the shell command directly and passes
# `$PATH` on as text (actions/runner ScriptHandler.cs, see `literal_shell`), so env sets PATH to the text `$PATH` and
# the set-up Python is not on it. Until round 4 the check read it as passing on the PATH the step started with, and did
# not report it.
COPILOT_PORTS_SUDO_YAML = (
    "on: push\njobs:\n  sudo-shell:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n"
    '        with: { python-version: "3.15" }\n      - name: Run\n        shell: sudo bash -e {0}\n'
    '        run: sudo env "PATH=$PATH" python3 x\n  path-shell:\n    runs-on: ubuntu-26.04\n    steps:\n'
    '      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n'
    '        shell: sudo env PATH="$PATH" bash -e {0}\n        run: sudo env "PATH=$PATH" python3 x\n'
)


def test_copilot_ports_a_sudo_shell_passes_on_only_its_own_secure_path():
    assert unset_steps("x.yml", read_jobs(COPILOT_PORTS_SUDO_YAML), {}) == [
        "x.yml > sudo-shell > Run > python",
        "x.yml > path-shell > Run > python",
    ]


# reader alignment: a step's keys after `-   `, and a matrix list at its key's indent.
ROUND_THREE_REVIEW_YAML_YAML = 'on: push\njobs:\n  spaced-dash:\n    runs-on: ubuntu-26.04\n    steps:\n      -   name: Run\n          run: node x\n  matrix-at-key:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix:\n        py:\n        - "3.15"\n    steps:\n      - uses: astral-sh/setup-uv@abc\n        with:\n          python-version: ${{ matrix.py }}\n      - name: Run\n        run: uv run x.py\n'


def test_round_three_review_yaml_workflow():
    jobs = read_jobs(ROUND_THREE_REVIEW_YAML_YAML)
    assert unset_steps("x.yml", jobs, {}) == ["x.yml > spaced-dash > Run > node"]
    assert pipx_problems("x.yml", jobs) == []


@pytest.mark.parametrize(
    "text",
    [
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - run: &a node x\n      - run: *a\n",
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - run: !!str node x\n",
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - env:\n          P: &p /usr/bin/python3\n        run: echo\n",
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - env:\n          P: !!str /usr/bin/python3\n        run: echo\n",
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - 'run': x\n",
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - run : x\n",
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - run:\n          node x\n",
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - env: {'A': x}\n        run: echo\n",
        'jobs:\n  j:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix:\n        py:\n          - "3.15"#x\n    steps:\n      - run: echo\n',
    ],
)
def test_round_three_review_readers_refuse_anchors_aliases_tags_and_unreadable_forms(text):
    with pytest.raises(AssertionError):
        read_jobs(text)


def test_round_three_review_a_long_quoted_string_and_a_long_script_read_quickly():
    """The review found 3,000 substitutions in one string took 31 seconds, and 4,000 such lines 13 seconds. The pre-PR
    review of Copilot's round-3 port fixes (HCW-HybridCloudWorks#1707) found a one-line `case` of 1,000 clauses with
    quoted words took 38."""
    started = time.perf_counter()
    quoted = 'echo "' + "$(true) x; " * 3000 + '"'
    lines = (
        "\n".join(f"unset P{i}; export -n Q{i}; eval 'echo {i}'" for i in range(4000))
        + "\npipx run x"
    )
    clauses = "case $k in " + 'b) env A="x" B="y" ;; ' * 1000 + "esac"
    for run in (quoted, lines, clauses):
        runs_runtime(run, "node")
        runs_through_sudo(run, "python")
        pipx_without_python(run, {"PIPX_DEFAULT_PYTHON": "/opt/py/bin/python3"})
    assert time.perf_counter() - started < 5


# Copilot on HCW-HybridCloudWorks#1722: bash runs `FOO=1 unset P`, `FOO=1 export -n P` and `FOO=1 declare +x P` like
# the builtin alone. The same cases as the website's scripts/workflow-runtime-setup.test.mjs, in the same order.
@pytest.mark.parametrize(
    ("run", "env", "flagged"),
    [
        (
            "FOO=1 unset PIPX_DEFAULT_PYTHON; bash -c 'pipx run x'",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            True,
        ),
        ("FOO=1 unset PIPX_DEFAULT_PYTHON; pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, True),
        (
            "FOO=1 export -n PIPX_DEFAULT_PYTHON; pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            True,
        ),
        (
            "FOO=1 declare +x PIPX_DEFAULT_PYTHON; bash -c 'pipx run x'",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            True,
        ),
        (
            'A=1 B="x y" export -n P; bash -c \'pipx run --python "$P" x\'',
            {"P": "/opt/py/bin/python3"},
            True,
        ),
        ('FOO=1 unset P; pipx run --python "$P" x', {"P": "/opt/py/bin/python3"}, True),
        ("FOO=1 export P=/opt/py/bin/python3; bash -c 'pipx run --python \"$P\" x'", {}, False),
        ('FOO=1 read P < p.txt; pipx run --python "$P" x', {}, False),
        (
            "FOO=1 unset -f PIPX_DEFAULT_PYTHON; pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            False,
        ),
        ("echo unset PIPX_DEFAULT_PYTHON; pipx run x", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, False),
    ],
)
def test_round_three_copilot_builtins_with_assignments_in_front_of_them(run, env, flagged):
    assert pipx_without_python(run, env) is flagged


# Copilot on HCW-HybridCloudWorks#1722 and HCW-NetworkEyes_App#399: the same cases as the website's
# scripts/workflow-runtime-setup.test.mjs, in the same order.
@pytest.mark.parametrize(
    ("run", "env", "flagged"),
    [
        # 5: `pipx` ends at an operator, as a runtime's name does, and not inside a `case` pattern.
        ("pipx;", {}, True),
        ("pipx | cat", {}, True),
        ("pipx &", {}, True),
        ("(pipx)", {}, True),
        ("pipx>log", {}, True),
        ("x=$(pipx)", {}, True),
        ("pipx run x;", {}, True),
        ("PIPX_DEFAULT_PYTHON=/p pipx;", {}, False),
        ("pipx) echo ;;", {}, False),
        ("pipx) pipx run x ;;", {}, True),
        # 6: sudo's reset of the environment holds through a later `env`, unless sudo keeps the variable.
        ('sudo env PATH="$PATH" pipx run x', {"PIPX_DEFAULT_PYTHON": "/opt/py"}, True),
        ("sudo env -S 'pipx run x'", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, True),
        ('sudo -E env PATH="$PATH" pipx run x', {"PIPX_DEFAULT_PYTHON": "/opt/py"}, False),
        (
            'sudo --preserve-env=PIPX_DEFAULT_PYTHON env PATH="$PATH" pipx run x',
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            False,
        ),
        ("sudo -E env -S 'pipx run x'", {"PIPX_DEFAULT_PYTHON": "/opt/py"}, False),
        # 1: a `#` line at a block value's content indentation is part of the value, so a value over two lines chooses nothing.
        ("pipx run x", {"PIPX_DEFAULT_PYTHON": "# note\n/opt/py/bin/python3"}, True),
    ],
)
def test_round_three_copilot_two_pipx_forms(run, env, flagged):
    assert pipx_without_python(run, env) is flagged


# 1, 2 and 4: block values, matrices and quotes, read as YAML reads them.
COPILOT_TWO_YAML = 'on: push\njobs:\n  comment-first-version:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: astral-sh/setup-uv@abc\n        with:\n          python-version: |-\n            # note\n            3.15\n      - name: Run\n        run: uv run x.py\n  comment-first-pipx:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        env:\n          PIPX_DEFAULT_PYTHON: |-\n            # note\n            /usr/bin/python3\n        run: pipx run x\n  matrix-expression:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix: ${{ fromJSON(needs.plan.outputs.matrix) }}\n    steps:\n      - uses: astral-sh/setup-uv@abc\n        with:\n          python-version: ${{ matrix.py }}\n      - name: Run\n        run: uv run x.py\n  escaped-quote:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: astral-sh/setup-uv@abc\n        with: { note: "a\\"b,c", python-version: "3.15" }\n      - name: Run\n        run: uv run x.py\n  single-quote:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: astral-sh/setup-uv@abc\n        with: { note: \'a\'\'b,c\', python-version: "3.15" }\n      - name: Run\n        run: uv run x.py\n  matrix-quoted-comma:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix:\n        py: ["3.15", "3.14,x"]\n    steps:\n      - uses: astral-sh/setup-uv@abc\n        with:\n          python-version: ${{ matrix.py }}\n      - name: Run\n        run: uv run x.py\n'


def test_round_three_copilot_two_block_values_matrices_and_quotes_read_as_yaml():
    jobs = read_jobs(COPILOT_TWO_YAML)
    assert unset_steps("x.yml", jobs, {}) == [
        "x.yml > comment-first-version > Run > python",
        "x.yml > matrix-expression > Run > python",
        "x.yml > matrix-quoted-comma > Run > python",
    ]
    assert pipx_problems("x.yml", jobs) == ["x.yml > comment-first-pipx > Scan > pipx"]


# 1, 2 and 3: the forms YAML or the line readers refuse.
@pytest.mark.parametrize(
    "text",
    [
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - env:\n          P: |-\n                \n            x\n        run: echo\n",
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix: [3.14]\n    steps:\n      - run: echo\n",
        "jobs:\n  j:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix: foo\n    steps:\n      - run: echo\n",
        'jobs:\n  j:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix:\n        py: ["3.15"]\n        oops\n    steps:\n      - run: echo\n',
    ],
)
def test_round_three_copilot_two_refused_forms(text):
    with pytest.raises(AssertionError):
        read_jobs(text)


# Copilot's third review of HCW-NetworkEyes_App#399: the same cases as the website's
# scripts/workflow-runtime-setup.test.mjs, in the same order. The latest change to PIPX_DEFAULT_PYTHON in a shell wins.
@pytest.mark.parametrize(
    ("run", "env", "flagged"),
    [
        (
            "PIPX_DEFAULT_PYTHON=/usr/bin/python3; PIPX_DEFAULT_PYTHON=/opt/py/bin/python3; pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            False,
        ),
        (
            "PIPX_DEFAULT_PYTHON=/usr/bin/python3; PIPX_DEFAULT_PYTHON=/opt/py/bin/python3; bash -c 'pipx run x'",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            False,
        ),
        (
            "PIPX_DEFAULT_PYTHON=/usr/bin/python3; PIPX_DEFAULT_PYTHON=/opt/py/bin/python3; pipx run x",
            {},
            True,
        ),
        (
            "export PIPX_DEFAULT_PYTHON=/usr/bin/python3; export PIPX_DEFAULT_PYTHON=/opt/py/bin/python3; pipx run x",
            {},
            False,
        ),
        (
            "PIPX_DEFAULT_PYTHON=/opt/py/bin/python3; PIPX_DEFAULT_PYTHON=/usr/bin/python3; pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            True,
        ),
        (
            "PIPX_DEFAULT_PYTHON=/opt/py/bin/python3; unset PIPX_DEFAULT_PYTHON; pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            True,
        ),
        (
            "unset PIPX_DEFAULT_PYTHON; export PIPX_DEFAULT_PYTHON=/opt/py/bin/python3; pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            False,
        ),
        (
            "unset PIPX_DEFAULT_PYTHON; PIPX_DEFAULT_PYTHON=/opt/py/bin/python3; pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            True,
        ),
        (
            "export -n PIPX_DEFAULT_PYTHON; export PIPX_DEFAULT_PYTHON; pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            False,
        ),
        (
            "export -n PIPX_DEFAULT_PYTHON; export PIPX_DEFAULT_PYTHON; bash -c 'pipx run x'",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            False,
        ),
        (
            "export -n PIPX_DEFAULT_PYTHON; bash -c 'pipx run x'",
            {"PIPX_DEFAULT_PYTHON": "/opt/py"},
            True,
        ),
        ("(export PIPX_DEFAULT_PYTHON=/opt/py/bin/python3); pipx run x", {}, True),
        ("bash -c 'export PIPX_DEFAULT_PYTHON=/opt/py/bin/python3; pipx run x'", {}, False),
    ],
)
def test_round_three_copilot_three_latest_change_wins(run, env, flagged):
    assert pipx_without_python(run, env) is flagged


# A `#` inside quotes in a one-line `[ ]` or `{ }` is part of the value, not a comment.
COPILOT_THREE_YAML = 'on: push\njobs:\n  matrix-hash:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix:\n        py: ["3.15 # floor"] # a comment\n    steps:\n      - uses: astral-sh/setup-uv@abc\n        with:\n          python-version: ${{ matrix.py }}\n      - name: Run\n        run: uv run x.py\n  flow-env-hash:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        env: { NOTE: "a # b", PIPX_DEFAULT_PYTHON: /opt/py/bin/python3 } # c\n        run: pipx run x\n  flow-with-quote:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: astral-sh/setup-uv@abc\n        with: { note: \'it\'\'s # x\', python-version: "3.15" }\n      - name: Run\n        run: uv run x.py\n'


def test_round_three_copilot_three_quoted_hash_in_one_line_values():
    jobs = read_jobs(COPILOT_THREE_YAML)
    assert unset_steps("x.yml", jobs, {}) == ["x.yml > matrix-hash > Run > python"]
    assert pipx_problems("x.yml", jobs) == []


# Copilot's review of the round-3 ports (#1707): the same cases as the website's
# scripts/workflow-runtime-setup.test.mjs, in the same order (Copilot on HCW-CloudCrawler_App#90,
# HCW-CloudCrawler_AddOn#79, HCW-NetworkEyes_AddOn#114 and HCW-MigrateOrchestrator_AddOn#77).
@pytest.mark.parametrize(
    ("line", "kind", "found"),
    [
        ("env PATH=/usr/bin python3 x.py", "python", True),
        ("PATH=/usr/bin python3 x.py", "python", True),
        ("PATH=/usr/bin:$PATH node x", "node", True),
        ("env PATH=/opt/x:$PATH node x", "node", True),
        ('PATH="/usr/bin" python3 x', "python", True),
        ('env "PATH=/usr/bin" python3 x', "python", True),
        ("PATH=/usr/bin bash -c 'python3 x'", "python", True),
        ("env PATH=/usr/bin env -S 'node x'", "node", True),
        ("x=$(PATH=/usr/bin node x)", "node", True),
        ("PATH=$PATH:/x python3 x", "python", False),
        ("PATH=$PATH python3 x", "python", False),
        ('env PATH="${PATH}:/x" node x', "node", False),
        ("PATH=/usr/bin echo; python3 x", "python", False),
        ("PATH=/usr/bin sudo env PATH=$PATH node x", "node", False),
        ("export PATH=/usr/bin; python3 x", "python", False),
    ],
)
def test_copilot_ports_a_command_whose_path_is_not_the_shells_is_reported(line, kind, found):
    assert runs_through_sudo(line, kind) is found


@pytest.mark.parametrize(
    ("line", "kind", "found"),
    [
        ("/usr/bin/python3 x", "python", True),
        ("/usr/local/bin/node x", "node", True),
        ("/usr/bin/node x", "node", True),
        ("/bin/python3 x", "python", True),
        ("/opt/az/bin/python3 x", "python", True),
        ("//usr/bin/../bin/python3 x", "python", True),
        ("/usr/local/bin/pipx run x", "python", True),
        ("python3.14 x", "python", True),
        ("python3.9 -V", "python", True),
        ('sudo env "PATH=$PATH" /usr/bin/python3 -V', "python", True),
        ("env PATH=$PATH python3.14 x", "python", True),
        ("bash -c '/usr/bin/python3 x'", "python", True),
        ("python3.15 x", "python", False),
        ("python3.15.2 x", "python", False),
        ("python3 x", "python", False),
        (".venv/bin/python x", "python", False),
        ("$pythonLocation/bin/python3 x", "python", False),
        ("/opt/hostedtoolcache/Python/3.15.0/x64/bin/python3 x", "python", False),
        ("./usr/bin/python3 x", "python", False),
        ("echo /usr/bin/python3", "python", False),
    ],
)
def test_copilot_ports_a_runner_folder_or_older_version_is_reported(line, kind, found):
    assert runs_through_sudo(line, kind) is found


@pytest.mark.parametrize(
    ("line", "kind", "found"),
    [
        ('case "$k" in a) node x ;; esac', "node", True),
        ('case "$k" in node) node x ;; esac', "node", True),
        ('case "$k" in a) echo ;; b) npm ci ;; esac', "node", True),
        ("case $k in (a) python3 x ;; esac", "python", True),
        ('case "$k" in a|b) echo ;& c) node x ;; esac', "node", True),
        ('if true; then case "$k" in a) node x;; esac; fi', "node", True),
        ('case "$k" in a) echo ;;& node) echo ;; esac', "node", False),
        ('case "$k" in node) echo ;; esac', "node", False),
        ('case "$k" in node | npm) echo ;; esac', "node", False),
        ("node|npm) echo hi ;;", "node", False),
        ("node) node x ;;", "node", True),
        ('echo "a;; node) x"', "node", False),
        ("case \"$k\" in a) bash -c 'node x' ;; esac", "node", True),
        ('case "$k" in node) env "PATH=$PATH" node x ;; esac', "node", True),
        ("case \"$k\" in a) bash <<'EOF' ;; esac\nnode x\nEOF", "node", True),
    ],
)
def test_copilot_ports_the_clauses_of_a_one_line_case_are_read(line, kind, found):
    assert runs_runtime(line, kind) is found


@pytest.mark.parametrize(
    ("line", "kind", "found"),
    [
        ('case "$k" in a) sudo node x ;; esac', "node", True),
        ('case "$k" in a) /usr/bin/python3 x ;; esac', "python", True),
        ('case "$k" in a) node x ;; esac', "node", False),
        ('case "$k" in a) sudo env "PATH=$PATH" node x ;; esac', "node", False),
        ("case \"$k\" in a) sudo bash -c 'node x' ;; esac", "node", True),
    ],
)
def test_copilot_ports_the_clauses_of_a_one_line_case_are_read_through_sudo(line, kind, found):
    assert runs_through_sudo(line, kind) is found


@pytest.mark.parametrize(
    ("run", "env", "flagged"),
    [
        ('case "$k" in a) pipx run x ;; esac', {}, True),
        ('case "$k" in pipx) echo ;; esac', {}, False),
        ('case "$k" in a) PIPX_DEFAULT_PYTHON=/opt/py/bin/python3 pipx run x ;; esac', {}, False),
    ],
)
def test_copilot_ports_pipx_in_a_one_line_case(run, env, flagged):
    assert pipx_without_python(run, env) is flagged


@pytest.mark.parametrize(
    ("run", "env", "shell", "flagged"),
    [
        (
            "pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/hostedtoolcache/Python/3.15.0/x64/bin/python3"},
            "env -u PIPX_DEFAULT_PYTHON bash -e script",
            True,
        ),
        (
            "pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/hostedtoolcache/Python/3.15.0/x64/bin/python3"},
            "env -i bash -e script",
            True,
        ),
        (
            "pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/hostedtoolcache/Python/3.15.0/x64/bin/python3"},
            "env PIPX_DEFAULT_PYTHON=/usr/bin/python3 bash -e script",
            True,
        ),
        (
            "pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/hostedtoolcache/Python/3.15.0/x64/bin/python3"},
            "sudo bash -e script",
            True,
        ),
        (
            "pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/hostedtoolcache/Python/3.15.0/x64/bin/python3"},
            "bash -e script",
            False,
        ),
        (
            "pipx run x",
            {"PIPX_DEFAULT_PYTHON": "/opt/hostedtoolcache/Python/3.15.0/x64/bin/python3"},
            "",
            False,
        ),
        ("pipx run x", {}, "env PIPX_DEFAULT_PYTHON=/opt/py/bin/python3 bash -e script", False),
        (
            "export PIPX_DEFAULT_PYTHON=/opt/py/bin/python3; pipx run x",
            {},
            "env -i bash -e script",
            False,
        ),
        ("pipx run --python /opt/py/bin/python3 x", {}, "env -i bash -e script", False),
    ],
)
def test_copilot_ports_the_words_of_the_steps_shell_reach_pipx(run, env, shell, flagged):
    assert pipx_without_python(run, env, {""}, None, shell) is flagged


PORTS_RUNNER_YAML = 'on: push\njobs:\n  path-env:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: env PATH=/usr/bin python3 x.py\n  path-assign:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: PATH=/usr/bin python3 x.py\n  path-kept:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: PATH=$PATH:/x python3 x.py\n  runner-path:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: /usr/bin/python3 x\n  versioned:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: python3.14 x\n  floor-name:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: python3.15 x\n  venv:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: .venv/bin/python x\n  runner-shell:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        shell: /usr/bin/python3 {0}\n        run: print(1)\n  versioned-shell:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        shell: python3.14 {0}\n        run: print(1)\n  path-shell:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        shell: env PATH=/usr/bin bash -e {0}\n        run: python3 x\n  sudo-runner:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: sudo env "PATH=$PATH" /usr/bin/python3 -V\n  node-runner:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-node@abc\n        with: { node-version: "26" }\n      - name: Run\n        run: /usr/local/bin/node x\n  node-kept:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-node@abc\n        with: { node-version: "26" }\n      - name: Run\n        run: node x\n  case-line:\n    runs-on: ubuntu-26.04\n    steps:\n      - name: Run\n        run: case "$k" in a) node x ;; esac\n'


def test_copilot_ports_runner_workflow():
    jobs = read_jobs(PORTS_RUNNER_YAML)
    assert unset_steps("x.yml", jobs, {}) == [
        "x.yml > path-env > Run > python",
        "x.yml > path-assign > Run > python",
        "x.yml > runner-path > Run > python",
        "x.yml > versioned > Run > python",
        "x.yml > runner-shell > Run > python",
        "x.yml > versioned-shell > Run > python",
        "x.yml > path-shell > Run > python",
        "x.yml > sudo-runner > Run > python",
        "x.yml > node-runner > Run > node",
        "x.yml > case-line > Run > node",
    ]
    assert pipx_problems("x.yml", jobs) == []


PORTS_MATRIX_YAML = 'on: push\nenv:\n  PIPX_DEFAULT_PYTHON: ${{ matrix.py }}\n  WPY: ${{ matrix.py }}\n  UVPY: ${{ matrix.uv }}\njobs:\n  workflow-level:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix:\n        py: [/opt/py/bin/python3]\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        run: pipx run x\n  job-level:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix:\n        py: [/opt/py/bin/python3]\n    env:\n      PIPX_DEFAULT_PYTHON: ${{ matrix.py }}\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        run: pipx run x\n  step-level:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix:\n        py: [/opt/py/bin/python3]\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        env:\n          PIPX_DEFAULT_PYTHON: ${{ matrix.py }}\n        run: pipx run x\n  step-reads-workflow:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix:\n        py: [/opt/py/bin/python3]\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        env:\n          PIPX_DEFAULT_PYTHON: ${{ env.WPY }}\n        run: pipx run x\n  script-reads-workflow:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix:\n        py: [/opt/py/bin/python3]\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        env:\n          PIPX_DEFAULT_PYTHON: ""\n        run: pipx run --python ${{ env.WPY }} x\n  script-matrix:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix:\n        py: [/opt/py/bin/python3]\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        env:\n          PIPX_DEFAULT_PYTHON: ""\n        run: pipx run --python ${{ matrix.py }} x\n  uv-workflow-level:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix:\n        uv: ["3.15"]\n    steps:\n      - uses: astral-sh/setup-uv@abc\n        with:\n          python-version: ${{ env.UVPY }}\n      - name: Run\n        run: uv run x.py\n  uv-job-level:\n    runs-on: ubuntu-26.04\n    strategy:\n      matrix:\n        uv: ["3.15"]\n    env:\n      UVPY: ${{ matrix.uv }}\n    steps:\n      - uses: astral-sh/setup-uv@abc\n        with:\n          python-version: ${{ env.UVPY }}\n      - name: Run\n        run: uv run x.py\n'


def test_copilot_ports_a_matrix_value_in_the_workflow_env_is_not_read():
    jobs = read_jobs(PORTS_MATRIX_YAML)
    assert unset_steps("x.yml", jobs, {}) == ["x.yml > uv-workflow-level > Run > python"]
    assert pipx_problems("x.yml", jobs) == [
        "x.yml > workflow-level > Scan > pipx",
        "x.yml > step-reads-workflow > Scan > pipx",
        "x.yml > script-reads-workflow > Scan > pipx",
    ]


PORTS_SHELL_YAML = 'on: push\njobs:\n  bash:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        shell: bash -e {0}\n        env:\n          PIPX_DEFAULT_PYTHON: /opt/hostedtoolcache/Python/3.15.0/x64/bin/python3\n        run: pipx run x\n  unset:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        shell: env -u PIPX_DEFAULT_PYTHON bash -e {0}\n        env:\n          PIPX_DEFAULT_PYTHON: /opt/hostedtoolcache/Python/3.15.0/x64/bin/python3\n        run: pipx run x\n  clear:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        shell: env -i bash -e {0}\n        env:\n          PIPX_DEFAULT_PYTHON: /opt/hostedtoolcache/Python/3.15.0/x64/bin/python3\n        run: pipx run x\n  runner:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        shell: env PIPX_DEFAULT_PYTHON=/usr/bin/python3 bash -e {0}\n        env:\n          PIPX_DEFAULT_PYTHON: /opt/hostedtoolcache/Python/3.15.0/x64/bin/python3\n        run: pipx run x\n  shell-sets:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        shell: env PIPX_DEFAULT_PYTHON=/opt/py/bin/python3 bash -e {0}\n        run: pipx run x\n  job-default:\n    runs-on: ubuntu-26.04\n    defaults:\n      run:\n        shell: env -u PIPX_DEFAULT_PYTHON bash -e {0}\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Scan\n        env:\n          PIPX_DEFAULT_PYTHON: /opt/hostedtoolcache/Python/3.15.0/x64/bin/python3\n        run: pipx run x\n'


def test_copilot_ports_the_words_of_a_steps_shell_reach_pipx_in_a_workflow():
    jobs = read_jobs(PORTS_SHELL_YAML)
    # Copilot's second round on the ports (HCW-HybridCloudWorks#1707): `env -i` clears PATH, so the `clear` job's pipx
    # is the runner's too.
    assert unset_steps("x.yml", jobs, {}) == ["x.yml > clear > Scan > python"]
    assert pipx_problems("x.yml", jobs) == [
        "x.yml > unset > Scan > pipx",
        "x.yml > clear > Scan > pipx",
        "x.yml > runner > Scan > pipx",
        "x.yml > job-default > Scan > pipx",
    ]


# Copilot's review of the round-3 ports (#1707), pre-PR review: the same cases as the website's
# scripts/workflow-runtime-setup.test.mjs, in the same order.
@pytest.mark.parametrize(
    ("line", "kind", "found"),
    [
        ("env -u PATH node x", "node", True),
        ("env --unset=PATH node x", "node", True),
        ("env --unset PATH node x", "node", True),
        ("env -uPATH python3 x", "python", True),
        ("env --un PATH python3 x", "python", True),
        ("env -i -u PATH node x", "node", True),
        ("sudo env -u PATH node x", "node", True),
        ("command -p python3 x", "python", True),
        ("command -p -- node x", "node", True),
        # Copilot's second round on the ports (HCW-HybridCloudWorks#1707): the last PATH given to env wins, and
        # `$PATH` is the shell's.
        ("env -u PATH PATH=$PATH node x", "node", False),
        ("env -u FOO node x", "node", False),
        ("env --unset=FOO python3 x", "python", False),
        ("env -C /tmp node x", "node", False),
        ("env -u FOO PATH=$PATH node x", "node", False),
        ("command python3 x", "python", False),
        ("command -v python3", "python", False),
        ("command -- node x", "node", False),
    ],
)
def test_copilot_ports_review_a_runtime_on_the_default_path_is_reported(line, kind, found):
    assert runs_through_sudo(line, kind) is found


@pytest.mark.parametrize(
    ("line", "kind", "found"),
    [
        ("python3.14t x", "python", True),
        ("python3.15t x", "python", True),
        ("python3t x", "python", True),
        ("/usr/bin/python3.15t x", "python", True),
        ("python3.15tx x", "python", False),
        ("echo python3.14t", "python", False),
    ],
)
def test_copilot_ports_review_free_threaded_names_are_python(line, kind, found):
    assert runs_runtime(line, kind) is found


@pytest.mark.parametrize(
    ("line", "kind", "found"),
    [
        ("python3.14t x", "python", True),
        ("python3.15t x", "python", False),
        # 3.15.1 is below the floor since it moved to 3.15.2 (owner decision 2026-11-14, HCW-HybridCloudWorks#1707).
        ("python3.15.1t x", "python", True),
        ("python3.9t x", "python", True),
        ("/usr/bin/python3.15t x", "python", True),
        (".venv/bin/python3.15t x", "python", False),
    ],
)
def test_copilot_ports_review_free_threaded_versions_are_read(line, kind, found):
    assert runs_through_sudo(line, kind) is found


@pytest.mark.parametrize(
    ("version", "kind", "below"),
    [
        ("3.14t", "python", True),
        ("3.15t", "python", False),
        # Below the floor since it moved to 3.15.2 (owner decision 2026-11-14, HCW-HybridCloudWorks#1707).
        ("3.15.1t", "python", True),
        ("3.16t", "python", False),
        ("3.x", "python", False),
        ("26t", "node", None),
    ],
)
def test_copilot_ports_review_a_free_threaded_version_meets_the_floor_by_its_number(
    version, kind, below
):
    assert _below_floor(version, kind) is below


@pytest.mark.parametrize(
    ("run", "env", "flagged"),
    [
        ("pipx run --python /usr/bin/python3.15t x", {}, True),
        ("pipx run --python /usr/local/bin/python3.14t x", {}, True),
        # Copilot's second round on the ports (HCW-MigrateOrchestrator_AddOn#77): only `python3.15` itself counts.
        ("pipx run --python python3.15t x", {}, True),
        ("pipx run --python python3.14t x", {}, True),
    ],
)
def test_copilot_ports_review_free_threaded_paths_given_to_pipx(run, env, flagged):
    assert pipx_without_python(run, env) is flagged


PRE_PR_YAML = 'on: push\njobs:\n  below:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: python3.14t x\n  floor:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: python3.15t x\n  no-set-up:\n    runs-on: ubuntu-26.04\n    steps:\n      - name: Run\n        run: python3.15t x\n  unset-path:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: env -u PATH python3 x\n  command-p:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-node@abc\n        with: { node-version: "26" }\n      - name: Run\n        run: command -p node x\n  unset-other:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-node@abc\n        with: { node-version: "26" }\n      - name: Run\n        run: env -u FOO node x\n'


def test_copilot_ports_review_workflow():
    jobs = read_jobs(PRE_PR_YAML)
    assert unset_steps("x.yml", jobs, {}) == [
        "x.yml > below > Run > python",
        "x.yml > no-set-up > Run > python",
        "x.yml > unset-path > Run > python",
        "x.yml > command-p > Run > node",
    ]
    assert pipx_problems("x.yml", jobs) == []


# Copilot's second round on the round-3 ports (#1707): the same cases as the website's
# scripts/workflow-runtime-setup.test.mjs, in the same order (Copilot on HCW-HybridCloudWorks#1723,
# HCW-CloudCrawler_App#90, HCW-CloudCrawler_AddOn#79, HCW-MigrateOrchestrator_AddOn#77 and HCW-CloudAssessor_AddOn#101).
@pytest.mark.parametrize(
    ("line", "kind", "found"),
    [
        ("python3t x", "python", True),
        ('sudo env "PATH=$PATH" python3t x', "python", True),
        (".venv/bin/python3t x", "python", False),
        ("python3.15t x", "python", False),
        ("python3 x", "python", False),
        ("env -i python3 x", "python", True),
        ("env --ignore-environment python3 x", "python", True),
        ("env --ignore-env python3 x", "python", True),
        ("env - python3 x", "python", True),
        ("env -i -C /tmp node x", "node", True),
        ("env -iu FOO node x", "node", True),
        ("env -i FOO=1 node x", "node", True),
        ("sudo env -i python3 x", "python", True),
        ("env -i PATH=/usr/bin:$PATH python3 x", "python", True),
        ("PATH=/usr/bin PATH=$PATH node x", "node", True),
        ("env -i PATH=$PATH python3 x", "python", False),
        ("env -u PATH PATH=$PATH node x", "node", False),
        ("env PATH=/usr/bin PATH=$PATH node x", "node", False),
        ("PATH=/usr/bin env PATH=$PATH node x", "node", False),
        ("sudo env -i PATH=$PATH node x", "node", False),
        ("env -i env PATH=$PATH node x", "node", False),
        ("env -v python3 x", "python", False),
    ],
)
def test_copilot_second_round_python3t_and_a_cleared_path(line, kind, found):
    assert runs_through_sudo(line, kind) is found


@pytest.mark.parametrize(
    ("run", "env", "flagged"),
    [
        ("pipx run --python python3.15t x", {}, True),
        ("pipx run --python python3.15 x", {}, False),
    ],
)
def test_copilot_second_round_pipx_names(run, env, flagged):
    assert pipx_without_python(run, env) is flagged


INDIRECT_SUDO_YAML = 'on: push\njobs:\n  sudo-shell:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-node@abc\n        with: { node-version: "26" }\n      - name: Build\n        shell: sudo bash -e {0}\n        run: make build\n  path-shell:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-node@abc\n        with: { node-version: "26" }\n      - name: Build\n        shell: env PATH=/usr/bin bash -e {0}\n        run: make build\n  clear-shell:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-node@abc\n        with: { node-version: "26" }\n      - name: Build\n        shell: env -i bash -e {0}\n        run: make build\n  plain-shell:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-node@abc\n        with: { node-version: "26" }\n      - name: Build\n        shell: bash -e {0}\n        run: make build\n  no-shell:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-node@abc\n        with: { node-version: "26" }\n      - name: Build\n        run: make build\n  no-set-up:\n    runs-on: ubuntu-26.04\n    steps:\n      - name: Build\n        run: make build\n  free-threaded:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: python3t x\n  cleared:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: env -i python3 x\n  restored:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: env -i PATH=$PATH python3 x\n'


def test_copilot_second_round_indirect_step_under_sudo():
    indirect = {
        "x.yml > sudo-shell > Build > node": "runs node through make",
        "x.yml > path-shell > Build > node": "runs node through make",
        "x.yml > clear-shell > Build > node": "runs node through make",
        "x.yml > plain-shell > Build > node": "runs node through make",
        "x.yml > no-shell > Build > node": "runs node through make",
        "x.yml > no-set-up > Build > node": "runs node through make",
    }
    assert unset_steps("x.yml", read_jobs(INDIRECT_SUDO_YAML), indirect) == [
        "x.yml > sudo-shell > Build > node",
        "x.yml > path-shell > Build > node",
        "x.yml > clear-shell > Build > node",
        "x.yml > no-set-up > Build > node",
        "x.yml > free-threaded > Run > python",
        "x.yml > cleared > Run > python",
    ]


ONE_LINE_DEFAULTS_YAML = 'on: push\ndefaults: {run: {shell: "python {0}"}}\njobs:\n  inherits:\n    runs-on: ubuntu-26.04\n    steps:\n      - name: Run\n        run: print(1)\n  set-up:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: print(1)\n  own-bash:\n    runs-on: ubuntu-26.04\n    defaults: {run: {shell: "bash -e {0}"}}\n    steps:\n      - name: Run\n        run: echo hi\n  own-comma:\n    runs-on: ubuntu-26.04\n    defaults: {run: {shell: \'python3 {0}\', working-directory: "a,b"}}\n    steps:\n      - name: Run\n        run: print(1)\n  own-block:\n    runs-on: ubuntu-26.04\n    defaults:\n      run: {shell: "sh -e {0}"}\n    steps:\n      - name: Run\n        run: echo hi\n'


def test_copilot_second_round_one_line_defaults():
    assert unset_steps("x.yml", read_jobs(ONE_LINE_DEFAULTS_YAML), {}) == [
        "x.yml > inherits > Run > python",
        "x.yml > own-comma > Run > python",
    ]


@pytest.mark.parametrize(
    "text",
    [
        "on: push\ndefaults: { run: { shell: bash -e {0} } }\njobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - run: echo\n",
        'on: push\ndefaults: {run: {shell: "python {0}"}\njobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - run: echo\n',
        "on: push\njobs:\n  j:\n    runs-on: ubuntu-26.04\n    defaults:\n      run: { shell: python {0} }\n    steps:\n      - run: echo\n",
        "on: push\njobs:\n  j:\n    runs-on: ubuntu-26.04\n    defaults: {run: {shell: 'python {0}}}\n    steps:\n      - run: echo\n",
        # A closer that does not match its opener (Copilot on HCW-NetworkEyes_App#402).
        'on: push\ndefaults: {run: {shell: "python {0}"]}\njobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - run: echo\n',
        'on: push\ndefaults: {run: {shell: "python {0}"}]\njobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps:\n      - run: echo\n',
    ],
)
def test_copilot_second_round_one_line_defaults_refused(text):
    with pytest.raises(AssertionError):
        read_jobs(text)


# Round 4 (HCW-HybridCloudWorks#1707). coproc (Copilot on HCW-MigrateOrchestrator_AddOn#77): bash runs the command
# after `coproc` in the background. A NAME may come first only before a compound command (`coproc NAME { ...; }`,
# `coproc NAME while ...`); before a simple command the first word is the command, so `coproc NAME node x` runs NAME,
# not node.
@pytest.mark.parametrize(
    ("line", "kind", "found"),
    [
        ("coproc node x.js", "node", True),
        ("coproc python3 x.py", "python", True),
        ("coproc NAME { node x; }", "node", True),
        ("coproc { python3 x; }", "python", True),
        ("coproc NAME ( node x )", "node", True),
        ("coproc NAME while node x; do :; done", "node", True),
        ("coproc until python3 x; do :; done", "python", True),
        ("coproc NAME if node x; then :; fi", "node", True),
        ("coproc FOO=1 node x", "node", True),
        ("coproc bash -c 'node x'", "node", True),
        ("x; coproc python3 y", "python", True),
        ("coproc NAME node x", "node", False),
        ("coproc NAME bash -c 'node x'", "node", False),
        ("coproc echo node", "node", False),
        ("echo coproc node", "node", False),
        ("echo 'coproc node x'", "node", False),
        ('echo "coproc python3 x"', "python", False),
        ("coprocnode x", "node", False),
    ],
)
def test_round_four_coproc_runs_its_command(line, kind, found):
    assert runs_runtime(line, kind) is found


@pytest.mark.parametrize(
    ("line", "kind", "found"),
    [
        ("coproc sudo python3 x", "python", True),
        ("coproc python3 x", "python", False),
        ("coproc /usr/bin/python3 x", "python", True),
        ("coproc NAME /usr/bin/python3 x", "python", False),
    ],
)
def test_round_four_coproc_through_sudo(line, kind, found):
    assert runs_through_sudo(line, kind) is found


@pytest.mark.parametrize(
    ("run", "env", "flagged"),
    [
        ("coproc pipx run x", {}, True),
        ("coproc PIPX_DEFAULT_PYTHON=/opt/py/bin/python3 pipx run x", {}, False),
        ("coproc NAME { pipx run x; }", {}, True),
        ("coproc NAME pipx run x", {}, False),
        ("coproc pipx run --python /opt/py/bin/python3 x", {}, False),
    ],
)
def test_round_four_coproc_pipx(run, env, flagged):
    assert pipx_without_python(run, env) is flagged


COPROC_YAML = 'on: push\njobs:\n  no-set-up:\n    runs-on: ubuntu-26.04\n    steps:\n      - name: Run\n        run: coproc node x\n  set-up:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-node@abc\n        with: { node-version: "26" }\n      - name: Run\n        run: coproc node x\n  named:\n    runs-on: ubuntu-26.04\n    steps:\n      - name: Run\n        run: coproc NAME node x\n  named-loop:\n    runs-on: ubuntu-26.04\n    steps:\n      - name: Run\n        run: coproc READER while python3 x; do :; done\n'


def test_round_four_coproc_workflow():
    assert unset_steps("x.yml", read_jobs(COPROC_YAML), {}) == [
        "x.yml > no-set-up > Run > node",
        "x.yml > named-loop > Run > python",
    ]


# The runner does not run a custom `shell:` through a shell (Copilot on HCW-MigrateOrchestrator_AddOn#77): it splits the
# program off at the first space and hands the rest, `{0}` filled in, to .NET, which splits it at spaces outside double
# quotes and drops those quotes, and fills nothing in (actions/runner ScriptHandlerHelpers.cs `ParseShellOptionString`;
# dotnet/runtime ProcessUtils.Unix.cs `GetNextArgument`). `$PATH` there is text.
@pytest.mark.parametrize(
    ("shell", "words"),
    [
        ("bash -e {0}", "bash -e script"),
        ('sudo env PATH="$PATH" bash -e {0}', "sudo env PATH=\x03PATH bash -e script"),
        ("env PATH=$PATH bash -e {0}", "env PATH=\x03PATH bash -e script"),
        ('bash -c "node x" {0}', "bash -c 'node x' script"),
        ("env 'A=1' bash {0}", "env ''\"'\"'A=1'\"'\"'' bash script"),
        ('bash -e "{0}"', "bash -e script"),
        ("node  {0}", "node script"),
        ('"bash" -e {0}', "'\"bash\"' -e script"),
        (
            "env PIPX_DEFAULT_PYTHON=$pythonLocation/bin/python3 bash -e {0}",
            "env PIPX_DEFAULT_PYTHON=\x03pythonLocation/bin/python3 bash -e script",
        ),
        ('bash -e {0} a\\"b', "bash -e script 'a\"b'"),
        ("bash -e {0} *", "bash -e script '*'"),
        ("python", "python"),
        ("", ""),
    ],
)
def test_round_four_a_shell_is_the_words_the_runner_passes_on(shell, words):
    assert step_shell({"shell": shell, "run": "x"}, {}) == words


LITERAL_SHELL_YAML = 'on: push\njobs:\n  path-shell:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        shell: sudo env PATH="$PATH" bash -e {0}\n        run: python3 x\n  env-path-shell:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        shell: env PATH="$PATH" bash -e {0}\n        run: python3 x\n  plain-shell:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        shell: bash -e {0}\n        run: python3 x\n  location-pipx:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        shell: env PIPX_DEFAULT_PYTHON=$pythonLocation/bin/python3 bash -e {0}\n        run: pipx run x\n  double-quoted-pipx:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        shell: env PIPX_DEFAULT_PYTHON="/opt/py/bin/python3" bash -e {0}\n        run: pipx run x\n  single-quoted-pipx:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        shell: env \'PIPX_DEFAULT_PYTHON=/opt/py/bin/python3\' bash -e {0}\n        run: pipx run x\n'


def test_round_four_a_literal_path_or_pipx_setting_in_a_shell():
    jobs = read_jobs(LITERAL_SHELL_YAML)
    assert unset_steps("x.yml", jobs, {}) == [
        "x.yml > path-shell > Run > python",
        "x.yml > env-path-shell > Run > python",
    ]
    assert pipx_problems("x.yml", jobs) == [
        "x.yml > location-pipx > Run > pipx",
        "x.yml > single-quoted-pipx > Run > pipx",
    ]


# Owner decision 2026-11-14: Python's floor is the newest patch of the newest line (3.15.2), not N-2 (3.15.0).
@pytest.mark.parametrize(
    ("version", "kind", "below"),
    [
        ("3.15.0", "python", True),
        ("3.15.1", "python", True),
        ("3.15.2", "python", False),
        ("3.15.3", "python", False),
        ("3.15", "python", False),
        ("3.15.x", "python", False),
        ("3.16.0", "python", False),
        ("3.15.1t", "python", True),
        ("3.15.2t", "python", False),
        ("3.14", "python", True),
    ],
)
def test_round_four_python_is_held_to_the_newest_patch(version, kind, below):
    assert _below_floor(version, kind) is below


@pytest.mark.parametrize(
    ("line", "kind", "found"),
    [
        ("python3.15.0 x", "python", True),
        ("python3.15.1 x", "python", True),
        ("python3.15.2 x", "python", False),
        ("python3.15.3 x", "python", False),
        ("python3.15 x", "python", False),
        ("python3.16.0 x", "python", False),
    ],
)
def test_round_four_a_python_named_below_the_newest_patch(line, kind, found):
    assert runs_through_sudo(line, kind) is found


@pytest.mark.parametrize(
    ("run", "env", "flagged"),
    [("pipx run --python python3.15 x", {}, False), ("pipx run --python python3.15.2 x", {}, True)],
)
def test_round_four_pipx_names_at_the_floor(run, env, flagged):
    assert pipx_without_python(run, env) is flagged


FLOOR_YAML = 'on: push\njobs:\n  exact-below:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15.1" }\n      - name: Run\n        run: python3 x\n  exact-at:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15.2" }\n      - name: Run\n        run: python3 x\n  line:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: actions/setup-python@abc\n        with: { python-version: "3.15" }\n      - name: Run\n        run: python3 x\n  uv-below:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: astral-sh/setup-uv@abc\n        with: { python-version: "3.15.1" }\n      - name: Run\n        run: uv run x.py\n  uv-at:\n    runs-on: ubuntu-26.04\n    steps:\n      - uses: astral-sh/setup-uv@abc\n        with: { python-version: "3.15.2" }\n      - name: Run\n        run: uv run x.py\n'


def test_round_four_a_set_up_step_below_the_newest_patch():
    jobs = read_jobs(FLOOR_YAML)
    assert floor_problems("x.yml", jobs) == [
        "x.yml > exact-below > step 1 > python: asks for 3.15.1, below the floor",
        "x.yml > uv-below > step 1 > python: asks for 3.15.1, below the floor",
    ]
    assert unset_steps("x.yml", jobs, {}) == ["x.yml > uv-below > Run > python"]


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


# What a reported step needs, for either of the two reasons a step is reported (round 3 review,
# HCW-HybridCloudWorks#1707).
UNSET_HELP = (
    "Each step listed runs Node.js or Python on the runner's own version. Either no set-up step is sure to have run "
    "before it: add actions/setup-node or actions/setup-python (or astral-sh/setup-uv with a python-version) before "
    "it, under the same if: as the step. Or it runs the runtime through sudo, which looks commands up on its own fixed "
    'list of folders (secure_path) and so finds the runner\'s: write `sudo env "PATH=$PATH" ...` so the set-up version '
    "is found. A step kept that way on purpose goes in RUNNER_DEFAULT_ALLOWED with its reason."
)


def test_every_step_that_runs_node_or_python_comes_after_its_version_is_set_up():
    assert [entry for entry in UNSET if entry not in RUNNER_DEFAULT_ALLOWED] == [], UNSET_HELP


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
