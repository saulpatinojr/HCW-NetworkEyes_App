"""The Docker Scout scan survives a refused scanner download, and a scan that did not run still fails the job (#427).

``docker/scout-action`` downloads its scanner (``docker-scout-action_linux_amd64``, 187 MB) when it starts, and it
asks GitHub's API for the file without a token. GitHub allows 60 such requests an hour per network address, the
runners share their addresses, and a spent allowance answers ``Unexpected HTTP response: 403`` before any image is
scanned (run 45321550784; https://github.com/docker/scout-action/issues/116). ``200-build-images.yml`` therefore
runs ``scripts/ci/seed_scout_scanner.sh`` before the first Scout step of every job: it fetches the same file with
the job's token, checks it against the sha256 in ``scripts/ci/scout_scanner_pins.txt`` and puts it in the action's
``dist/`` folder, where the action looks before it downloads.

Two things are held here.

* The workflow: every job that runs Scout fetches the scanner first, the Scout steps keep their gate exactly
  (by digest, fixable critical and high, ``exit-code``), nothing on that path may continue after an error, and every
  pinned commit of the action has a row in the pins file.
* The script, run for real with stand-ins for ``gh`` and ``curl``: a good file is installed; a file that cannot be
  fetched is a warning and nothing is installed, so the action downloads as before; a file with the wrong sha256
  stops the job and is never installed.

The stand-ins do not prove that GitHub accepts the job's token for another repository's release, or that the
runner keeps its actions where the script looks; only a real run of ``200-build-images.yml`` shows those, and when
either is not so the script warns and the Scout step behaves as it did before this change.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
BUILD = WORKFLOWS / "200-build-images.yml"
SCRIPT = REPO_ROOT / "scripts" / "ci" / "seed_scout_scanner.sh"
PINS = REPO_ROOT / "scripts" / "ci" / "scout_scanner_pins.txt"

SCOUT_ACTION = "docker/scout-action@"
SEED_RUN = "bash scripts/ci/seed_scout_scanner.sh"
ASSET = "docker-scout-action_linux_amd64"
#: The jobs that scan, and how many images each scans.
SCOUT_JOBS = {"build-images": 1, "build-web": 2, "rehearse-docker-login": 1}

PIN_ROW = re.compile(r"^([0-9a-f]{40}) (v\d+\.\d+\.\d+) ([0-9a-f]{64})$")
USES_LINE = re.compile(
    r"uses:\s*docker/scout-action@([0-9a-f]{40})\s+#\s*(v\d+\.\d+\.\d+)\s*$", re.M
)


def _pins() -> dict[str, tuple[str, str]]:
    rows = {}
    for line in PINS.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        match = PIN_ROW.match(line)
        assert match, f"not '<commit> v<N.N.N> <sha256>': {line!r}"
        assert match[1] not in rows, f"two rows for {match[1]}"
        rows[match[1]] = (match[2], match[3])
    return rows


def _jobs() -> dict[str, dict]:
    return yaml.safe_load(BUILD.read_text(encoding="utf-8"))["jobs"]


def _is_scout(step: dict) -> bool:
    return str(step.get("uses", "")).startswith(SCOUT_ACTION)


def _is_seed(step: dict) -> bool:
    return "seed_scout_scanner" in str(step.get("run", ""))


# --- the workflow ---------------------------------------------------------------------------------------------


class TestEveryScoutStepHasTheScannerFetchedFirst:
    def test_the_jobs_that_scan_are_the_ones_expected(self):
        found = {
            name: sum(_is_scout(s) for s in job.get("steps", []))
            for name, job in _jobs().items()
            if any(_is_scout(s) for s in job.get("steps", []))
        }
        assert found == SCOUT_JOBS

    def test_no_other_workflow_runs_scout(self):
        # A Scout step added to another workflow would not have the fetch in front of it; bring it under this test.
        for path in sorted(WORKFLOWS.glob("*.yml")):
            if path != BUILD:
                assert SCOUT_ACTION not in path.read_text(encoding="utf-8"), path.name

    @pytest.mark.parametrize("job_name", sorted(SCOUT_JOBS))
    def test_the_fetch_runs_once_before_the_first_scout_step(self, job_name):
        steps = _jobs()[job_name]["steps"]
        seeds = [i for i, s in enumerate(steps) if _is_seed(s)]
        scouts = [i for i, s in enumerate(steps) if _is_scout(s)]
        assert len(seeds) == 1, (
            "one fetch per job: a later Scout step finds the file already in place"
        )
        assert seeds[0] < scouts[0]
        checkout = next(
            i for i, s in enumerate(steps) if str(s.get("uses", "")).startswith("actions/checkout@")
        )
        assert checkout < seeds[0], "the script is a file of the repository"

    @pytest.mark.parametrize("job_name", sorted(SCOUT_JOBS))
    def test_the_fetch_step_is_the_plain_call_with_the_jobs_own_token(self, job_name):
        step = next(s for s in _jobs()[job_name]["steps"] if _is_seed(s))
        # No argument: the pins file is the one in the repository, never one a step could point elsewhere.
        assert step["run"] == SEED_RUN
        assert step["env"] == {"GH_TOKEN": "${{ github.token }}"}
        assert set(step) == {"name", "env", "run"}, "no `if`, no continue-on-error, no other shell"

    @pytest.mark.parametrize("job_name", sorted(SCOUT_JOBS))
    def test_the_scout_gate_is_exactly_as_strict_as_before(self, job_name):
        for step in (s for s in _jobs()[job_name]["steps"] if _is_scout(s)):
            assert step["with"]["command"] == "cves"
            assert step["with"]["only-severities"] == "critical,high"
            assert step["with"]["only-fixed"] is True
            assert step["with"]["exit-code"] is True
            assert re.search(r"@\$\{\{ steps\.\w+\.outputs\.digest \}\}$", step["with"]["image"]), (
                "by digest"
            )
            assert set(step) <= {"name", "id", "uses", "with"}, (
                "a Scout step takes no `if` and no continue-on-error: a scan that did not run fails the job"
            )

    def test_nothing_in_the_workflow_may_continue_after_an_error(self):
        assert "continue-on-error" not in BUILD.read_text(encoding="utf-8")

    def test_signing_still_comes_after_every_scan(self):
        for job_name in ("build-images", "build-web"):
            steps = _jobs()[job_name]["steps"]
            last_scout = max(i for i, s in enumerate(steps) if _is_scout(s))
            first_sign = min(
                i for i, s in enumerate(steps) if "sign_image.sh" in str(s.get("run", ""))
            )
            assert last_scout < first_sign, job_name
            for step in steps[last_scout:]:
                if "sign_image.sh" in str(step.get("run", "")):
                    assert "if" not in step, "signing runs only when every earlier step passed"

    def test_a_change_to_the_script_or_the_pins_starts_a_build(self):
        paths = yaml.safe_load(BUILD.read_text(encoding="utf-8"))[True]["push"]["paths"]
        assert "scripts/ci/seed_scout_scanner.sh" in paths
        assert "scripts/ci/scout_scanner_pins.txt" in paths


class TestThePinsFile:
    def test_every_pinned_commit_of_the_action_has_a_row_for_the_release_beside_it(self):
        pins = _pins()
        used = USES_LINE.findall(BUILD.read_text(encoding="utf-8"))
        assert len(used) == sum(SCOUT_JOBS.values()), (
            "every Scout step is `uses: ...@<40 hex>  # v<N.N.N>`"
        )
        assert len(set(used)) == 1, "one version of the action in the whole workflow"
        commit, version = used[0]
        assert commit in pins, (
            f"docker/scout-action@{commit} ({version}) has no row in scripts/ci/scout_scanner_pins.txt. Add "
            "'<commit> <release> <sha256 of docker-scout-action_linux_amd64>', with the sha256 GitHub shows beside "
            f"the file at https://github.com/docker/scout-action/releases/tag/{version}; until then the scanner is "
            "not fetched ahead and a refused download fails the build again (#427)."
        )
        assert pins[commit][0] == version

    def test_the_script_reads_the_pins_file_beside_it_and_is_executable(self):
        text = SCRIPT.read_text(encoding="utf-8")
        assert 'PINS="${1:-$HERE/scout_scanner_pins.txt}"' in text
        assert text.startswith("#!/usr/bin/env bash\n") and "set -euo pipefail" in text
        assert SCRIPT.stat().st_mode & stat.S_IXUSR


# --- the script, run for real -----------------------------------------------------------------------------------

COMMIT = "a" * 40
VERSION = "v9.8.7"
GOOD = b"the published scanner\n"
BAD = b"something else\n"

GH_STUB = """#!/usr/bin/env bash
echo "gh $*" >> "$CALLS"
[ "${GH_BEHAVIOUR}" = fail ] && { echo "HTTP 403: rate limit" >&2; exit 1; }
[ -n "${GH_TOKEN:-}" ] || { echo "gh ran without a token" >&2; exit 4; }
out=""
while [ $# -gt 0 ]; do [ "$1" = --output ] && out="$2"; shift; done
cp "$GH_PAYLOAD" "$out"
"""

CURL_STUB = """#!/usr/bin/env bash
echo "curl $*" >> "$CALLS"
[ "${CURL_BEHAVIOUR}" = fail ] && { echo "curl: (22) The requested URL returned error: 403" >&2; exit 22; }
out=""
while [ $# -gt 0 ]; do [ "$1" = --output ] && out="$2"; shift; done
cp "$CURL_PAYLOAD" "$out"
"""


class Runner:
    """A stand-in for the runner's folders: work/<repository> and work/_actions/docker/scout-action/<commit>."""

    def __init__(self, tmp_path: Path):
        self.tmp = tmp_path
        self.workspace = tmp_path / "work" / "repository"
        self.workspace.mkdir(parents=True)
        self.action = tmp_path / "work" / "_actions" / "docker" / "scout-action" / COMMIT
        self.action.mkdir(parents=True)
        (self.action / "index.js").write_text(
            f'async function main() {{\n\t    const version = "{VERSION}";\n}}\n', encoding="utf-8"
        )
        self.installed = self.action / "dist" / ASSET
        self.pins = tmp_path / "pins.txt"
        self.pins.write_text(
            f"# a comment\n{COMMIT} {VERSION} {hashlib.sha256(GOOD).hexdigest()}\n",
            encoding="utf-8",
        )
        self.good = tmp_path / "good"
        self.good.write_bytes(GOOD)
        self.bad = tmp_path / "bad"
        self.bad.write_bytes(BAD)
        self.calls = tmp_path / "calls"
        self.calls.write_text("", encoding="utf-8")
        self.temp = tmp_path / "runner-temp"
        self.temp.mkdir()
        stubs = tmp_path / "stubs"
        stubs.mkdir()
        for name, body in (("gh", GH_STUB), ("curl", CURL_STUB)):
            (stubs / name).write_text(body, encoding="utf-8")
            (stubs / name).chmod(0o755)
        self.env = {
            "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}",
            "RUNNER_WORKSPACE": str(self.workspace),
            "RUNNER_TEMP": str(self.temp),
            "SCOUT_SEED_PAUSE_SECONDS": "0",
            "GH_TOKEN": "stub",
            "CALLS": str(self.calls),
            "GH_BEHAVIOUR": "ok",
            "CURL_BEHAVIOUR": "ok",
            "GH_PAYLOAD": str(self.good),
            "CURL_PAYLOAD": str(self.good),
        }

    def run(self, **overrides: str | None) -> subprocess.CompletedProcess:
        env = dict(self.env)
        for key, value in overrides.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return subprocess.run(
            ["bash", str(SCRIPT), str(self.pins)],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def called(self) -> list[str]:
        return [line.split()[0] for line in self.calls.read_text(encoding="utf-8").splitlines()]

    def nothing_left_behind(self) -> bool:
        return not any(self.temp.iterdir())


@pytest.fixture
def runner(tmp_path) -> Runner:
    return Runner(tmp_path)


class TestTheScriptInstallsOnlyThePublishedFile:
    def test_the_file_fetched_with_the_token_is_installed_where_the_action_looks(self, runner):
        result = runner.run()
        assert result.returncode == 0, result.stdout + result.stderr
        assert runner.installed.read_bytes() == GOOD
        assert runner.installed.stat().st_mode & stat.S_IXUSR
        assert runner.called() == ["gh"], "the public link is not needed when the token worked"
        call = runner.calls.read_text(encoding="utf-8")
        assert f"release download {VERSION} --repo docker/scout-action --pattern {ASSET}" in call
        assert "::warning" not in result.stdout and "::error" not in result.stdout
        assert runner.nothing_left_behind()

    def test_when_the_token_route_is_refused_the_public_link_is_used(self, runner):
        result = runner.run(GH_BEHAVIOUR="fail")
        assert result.returncode == 0, result.stdout + result.stderr
        assert runner.installed.read_bytes() == GOOD
        assert runner.called() == ["gh", "curl"]
        assert (
            f"https://github.com/docker/scout-action/releases/download/{VERSION}/{ASSET}"
            in runner.calls.read_text(encoding="utf-8")
        )

    def test_without_a_token_only_the_public_link_is_tried(self, runner):
        result = runner.run(GH_TOKEN=None)
        assert result.returncode == 0, result.stdout + result.stderr
        assert runner.installed.read_bytes() == GOOD
        assert runner.called() == ["curl"]

    def test_a_file_that_cannot_be_fetched_is_a_warning_and_the_action_is_left_to_download(
        self, runner
    ):
        result = runner.run(GH_BEHAVIOUR="fail", CURL_BEHAVIOUR="fail")
        assert result.returncode == 0, (
            "the Scout step decides: it downloads itself, and fails the job if it cannot"
        )
        assert "::warning" in result.stdout
        assert "the job fails without scanning" in result.stdout
        assert not runner.installed.exists()
        assert not (runner.action / "dist").exists()
        assert runner.called() == ["gh", "curl"] * 3, "three attempts, both routes each"
        assert runner.nothing_left_behind()

    @pytest.mark.parametrize("route", ["gh", "curl"])
    def test_a_file_with_the_wrong_sha256_stops_the_job_and_is_never_installed(self, runner, route):
        overrides = (
            {"GH_PAYLOAD": str(runner.bad)}
            if route == "gh"
            else {"GH_BEHAVIOUR": "fail", "CURL_PAYLOAD": str(runner.bad)}
        )
        result = runner.run(**overrides)
        assert result.returncode == 1
        assert "::error::" in result.stdout
        assert hashlib.sha256(BAD).hexdigest() in result.stdout
        assert not runner.installed.exists()
        assert runner.nothing_left_behind()

    def test_a_file_already_in_place_is_checked_and_not_fetched_again(self, runner):
        assert runner.run().returncode == 0
        runner.calls.write_text("", encoding="utf-8")
        result = runner.run()
        assert result.returncode == 0
        assert "already in place" in result.stdout
        assert runner.called() == []

    def test_a_wrong_file_already_in_place_stops_the_job(self, runner):
        runner.installed.parent.mkdir()
        runner.installed.write_bytes(BAD)
        result = runner.run()
        assert result.returncode == 1
        assert "::error::" in result.stdout
        assert runner.called() == []
        assert runner.installed.read_bytes() == BAD, (
            "left as found, for whoever looks at the failed job"
        )

    def test_a_commit_without_a_row_gets_nothing_installed(self, runner):
        runner.pins.write_text(
            f"{'b' * 40} {VERSION} {hashlib.sha256(GOOD).hexdigest()}\n", encoding="utf-8"
        )
        result = runner.run()
        assert result.returncode == 0
        assert "::warning" in result.stdout and "has no row" in result.stdout
        assert not runner.installed.exists()
        assert runner.called() == []

    def test_an_action_that_asks_for_another_release_gets_nothing_installed(self, runner):
        # The action downloads the release its own code names; a file of any other release must not stand in.
        (runner.action / "index.js").write_text('    const version = "v9.8.6";\n', encoding="utf-8")
        result = runner.run()
        assert result.returncode == 0
        assert "::warning" in result.stdout and "does not ask for release" in result.stdout
        assert not runner.installed.exists()
        assert runner.called() == []

    def test_a_malformed_row_is_an_error(self, runner):
        runner.pins.write_text(f"{COMMIT} {VERSION} not-a-sha256\n", encoding="utf-8")
        result = runner.run()
        assert result.returncode == 1
        assert not runner.installed.exists()

    def test_a_runner_without_the_actions_folder_is_a_warning(self, runner):
        result = runner.run(RUNNER_WORKSPACE=str(runner.tmp / "elsewhere" / "repository"))
        assert result.returncode == 0
        assert "::warning" in result.stdout
        assert runner.called() == []

    def test_a_missing_pins_file_is_an_error(self, runner):
        runner.pins.unlink()
        result = runner.run()
        assert result.returncode == 1
        assert "::error::" in result.stdout
