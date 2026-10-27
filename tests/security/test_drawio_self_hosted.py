"""The diagram editor is served by this deployment: customer topology never goes to a public draw.io host.

``REVIEW.md`` R-019 / issue NE-9. The editor on the Diagram page is the draw.io web app, fetched at image build
(stage ``drawio-webapp`` of ``apps/network-assessment-web/Dockerfile``) and served under ``/drawio/`` with a Content-Security-Policy
that lets it talk to nothing but this origin and runs it in a sandbox. These checks keep that from coming back:

* ``TestTheEditorIsPinned`` — the release is pinned by version and sha256 at the top of the Dockerfile, the download
  URL is built from the pinned version, the checksum is verified before the unzip in one ``&&`` chain, the trim fails
  closed (the server side and the service worker are deleted and checked to be gone), the files are read-only, the
  licence travels with them, and the runner records the version in an image label.
* ``TestTheWeeklyPinCheck`` — the scheduled workflow that reminds the owner when the pin is behind.
* ``TestNoLiveFileNamesAPublicDrawioHost`` — no code, configuration, test or workflow file names a public draw.io,
  diagrams.net or drawio.com host. The only thing not read is the vendored editor itself (``public/drawio``), which
  is third-party code. The web tier has the same check in ``apps/network-assessment-web/lib/drawio-embed.test.ts``, next to the CSP,
  sandbox, header and embed-URL assertions.
* ``TestTheWebCspFramesOnlyThisOrigin`` — the application's own CSP has no draw.io host in ``frame-src`` or anywhere.

All of them are static reads of files. They do not prove what the running image serves; the vitest suite covers the
headers and a browser run against the built image is the proof that the editor loads and stays sandboxed
(``CHANGELOG.md``).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
THIS_FILE = Path(__file__).resolve()
DOCKERFILE = REPO_ROOT / "apps" / "network-assessment-web" / "Dockerfile"
MIDDLEWARE = REPO_ROOT / "apps" / "network-assessment-web" / "middleware.ts"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "380-drawio-pin-check.yml"

#: A URL, or a well-known bare host such as ``embed.<domain>``, under draw.io's, diagrams.net's or drawio.com's
#: domains. The product name written as prose ("the draw.io editor") is not a host and does not match.
PUBLIC_HOST = re.compile(
    r"(?://|\b(?:embed|viewer|app|www|icons|log|test)\.)(?:[a-z0-9-]+\.)*"
    r"(?:diagrams\.net|draw\.io|drawio\.com)(?![a-z0-9-])",
    re.IGNORECASE,
)

#: Where code, configuration and tests live. Documentation and history (markdown) are not scanned: they may name a
#: host to explain it.
SCANNED_ROOTS = ("apps", "network_assessment", "packages", "scripts", ".github", "infra", "tests")
SCANNED_FILES = ("Dockerfile", "docker-compose.yml", "pyproject.toml", ".env.example")
SKIPPED_DIRECTORIES = frozenset(
    {"node_modules", ".next", "__pycache__", ".ruff_cache", ".pytest_cache", ".mypy_cache", ".venv"}
)
#: The vendored editor (fetched at image build, git-ignored) names its own hosts; skipped at this path and nowhere else.
VENDORED_EDITOR = "apps/network-assessment-web/public/drawio"
#: The guards themselves spell hosts out to prove their matchers.
GUARD_FILES = frozenset({"apps/network-assessment-web/lib/drawio-embed.test.ts"})
MAX_BYTES = 2_000_000

VERSION = re.compile(r"^\d+\.\d+\.\d+$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _dockerfile() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def _stage(text: str, name: str) -> str:
    """The instructions of one build stage, from its FROM line to the next FROM."""
    match = re.search(
        rf"^FROM\s+\S+\s+AS\s+{re.escape(name)}\s*$(.*?)(?=^FROM\s|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"{DOCKERFILE.name} has no stage named {name}"
    return match.group(1)


def _runs(stage: str) -> list[str]:
    """Each RUN instruction of a stage as one line: backslash continuations joined, comments dropped."""
    lines = [line for line in stage.splitlines() if not line.lstrip().startswith("#")]
    joined = re.sub(r"\\\s*\n\s*", " ", "\n".join(lines) + "\n")
    return [line.strip()[4:].strip() for line in joined.splitlines() if line.startswith("RUN ")]


def _run_containing(stage: str, needle: str) -> str:
    matches = [run for run in _runs(stage) if needle in run]
    assert len(matches) == 1, f"expected exactly one RUN with {needle!r}, found {len(matches)}"
    return matches[0]


def _scanned_files() -> list[Path]:
    files: list[Path] = [REPO_ROOT / name for name in SCANNED_FILES if (REPO_ROOT / name).is_file()]
    for root in SCANNED_ROOTS:
        base = REPO_ROOT / root
        for directory, subdirectories, names in os.walk(base):
            here = Path(directory).relative_to(REPO_ROOT).as_posix()
            subdirectories[:] = sorted(
                d
                for d in subdirectories
                if d not in SKIPPED_DIRECTORIES and f"{here}/{d}" != VENDORED_EDITOR
            )
            for filename in sorted(names):
                path = Path(directory) / filename
                relative = path.relative_to(REPO_ROOT).as_posix()
                if (
                    relative in GUARD_FILES
                    or path.resolve() == THIS_FILE
                    or path.stat().st_size > MAX_BYTES
                ):
                    continue
                files.append(path)
    return files


class TestTheEditorIsPinned:
    def test_the_pin_is_a_version_and_a_sha256_declared_before_the_first_stage(self):
        text = _dockerfile()
        head = text[: re.search(r"^FROM\s", text, re.MULTILINE).start()]
        version = re.search(r"^ARG DRAWIO_WEBAPP_VERSION=(\S+)\s*$", head, re.MULTILINE)
        digest = re.search(r"^ARG DRAWIO_WEBAPP_SHA256=(\S+)\s*$", head, re.MULTILINE)
        assert version and VERSION.fullmatch(version.group(1)), (
            "DRAWIO_WEBAPP_VERSION must be an exact x.y.z"
        )
        assert digest and SHA256.fullmatch(digest.group(1)), (
            "DRAWIO_WEBAPP_SHA256 must be 64 lowercase hex digits"
        )
        assert len(re.findall(r"^ARG DRAWIO_WEBAPP_VERSION=", text, re.MULTILINE)) == 1
        assert len(re.findall(r"^ARG DRAWIO_WEBAPP_SHA256=", text, re.MULTILINE)) == 1

    def test_the_stage_and_the_runner_take_the_pin_from_the_top_without_redefining_it(self):
        for name in ("drawio-webapp", "runner"):
            stage = _stage(_dockerfile(), name)
            assert re.search(r"^ARG DRAWIO_WEBAPP_VERSION\s*$", stage, re.MULTILINE), name
        assert re.search(
            r"^ARG DRAWIO_WEBAPP_SHA256\s*$", _stage(_dockerfile(), "drawio-webapp"), re.MULTILINE
        )

    def test_the_download_uses_the_pinned_version(self):
        stage = _stage(_dockerfile(), "drawio-webapp")
        assert (
            "https://github.com/jgraph/drawio/releases/download/v${DRAWIO_WEBAPP_VERSION}/draw.war"
            in stage
        )

    def test_the_checksum_is_verified_before_the_unzip_in_one_and_chain(self):
        run = _run_containing(_stage(_dockerfile(), "drawio-webapp"), "sha256sum -c -")
        steps = [step.strip() for step in run.split("&&")]
        positions = {
            "download": next(i for i, s in enumerate(steps) if s.startswith("wget ")),
            "check": next(
                i
                for i, s in enumerate(steps)
                if s == 'echo "${DRAWIO_WEBAPP_SHA256}  /tmp/draw.war" | sha256sum -c -'
            ),
            "unzip": next(i for i, s in enumerate(steps) if s.startswith("unzip ")),
        }
        assert positions["download"] < positions["check"] < positions["unzip"], positions
        # `;` or `||` would let the build carry on after a failed checksum.
        assert ";" not in run, "no `;` in the download and verify step"
        assert "||" not in run, "no `||` in the download and verify step"

    def test_the_trim_fails_closed(self):
        run = _run_containing(_stage(_dockerfile(), "drawio-webapp"), "rm -rf WEB-INF")
        assert ";" not in run and "||" not in run, "no `;` or `||` in the trim step"
        steps = [step.strip() for step in run.split("&&")]
        # What must be deleted ...
        for gone in ("WEB-INF", "META-INF", "service-worker.js", "workbox-*.js"):
            assert any(s.startswith(("rm -rf", "rm -f")) and gone in s for s in steps), gone
        # ... is also checked to be gone, and what the editor needs is checked to be there.
        for absent in ("test ! -e WEB-INF", "test ! -e META-INF", "test ! -e service-worker.js"):
            assert absent in steps, absent
        assert any(s.startswith("test -z") and "workbox-" in s for s in steps)
        for needed in (
            "test -f index.html",
            "test -f js/app.min.js",
            "test -f resources/dia.txt",
            "test -f mxgraph/css/common.css",
        ):
            assert needed in steps, needed
        # The checks come last, after every deletion.
        last_delete = max(i for i, s in enumerate(steps) if s.startswith(("rm ", "find ")))
        first_check = min(i for i, s in enumerate(steps) if s.startswith("test "))
        assert last_delete < first_check

    def test_the_files_are_read_only_and_the_licence_travels_with_them(self):
        stage = _stage(_dockerfile(), "drawio-webapp")
        assert "COPY third-party/drawio/LICENSE /out/LICENSE" in stage
        run = _run_containing(stage, "chmod 444")
        assert "chmod 555" in run and "find /out -type f" in run and "find /out -type d" in run
        # The chmod comes after the licence is copied, so the licence is read-only too.
        assert stage.index("COPY third-party/drawio/LICENSE") < stage.index("chmod 444")
        licence = (
            REPO_ROOT / "apps" / "network-assessment-web" / "third-party" / "drawio" / "LICENSE"
        )
        assert "Apache License" in licence.read_text(encoding="utf-8")[:200]

    def test_the_runner_serves_the_editor_from_its_own_files_and_labels_the_version(self):
        runner = _stage(_dockerfile(), "runner")
        assert "COPY --from=drawio-webapp --chown=nextjs:nodejs /out ./app/public/drawio" in runner
        assert 'io.github.saulpatinojr.drawio-webapp.version="${DRAWIO_WEBAPP_VERSION}"' in runner

    def test_the_downloaded_files_are_not_committed(self):
        ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        assert "apps/network-assessment-web/public/drawio/" in ignored
        dockerignore = (
            (REPO_ROOT / "apps" / "network-assessment-web" / ".dockerignore")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        assert "public/drawio" in dockerignore


class TestTheWeeklyPinCheck:
    def _text(self) -> str:
        return WORKFLOW.read_text(encoding="utf-8")

    def test_it_runs_weekly_and_on_demand(self):
        text = self._text()
        assert re.search(r"^\s*schedule:\s*\n\s*- cron: '[^']+'", text, re.MULTILINE)
        assert re.search(r"^\s*workflow_dispatch:", text, re.MULTILINE)

    def test_it_can_read_the_repository_and_write_issues_and_nothing_else(self):
        document = yaml.safe_load(self._text())
        assert document["permissions"] == {"contents": "read"}
        assert list(document["jobs"]) == ["check"]
        assert document["jobs"]["check"]["permissions"] == {"contents": "read", "issues": "write"}

    def test_it_uses_no_secret_and_only_a_pinned_checkout_action(self):
        text = self._text()
        assert "secrets." not in text
        uses = re.findall(r"^\s*-?\s*uses:\s*(\S+)", text, re.MULTILINE)
        assert len(uses) == 1 and re.fullmatch(r"actions/checkout@[0-9a-f]{40}", uses[0]), uses
        assert "persist-credentials: false" in text

    def test_it_compares_the_dockerfile_pin_with_the_latest_release_and_the_advisories(self):
        text = self._text()
        assert (
            "ARG DRAWIO_WEBAPP_VERSION=" in text
            and "apps/network-assessment-web/Dockerfile" in text
        )
        assert "gh api repos/jgraph/drawio/releases/latest" in text
        assert "repos/jgraph/drawio/security-advisories" in text

    def test_it_keeps_one_issue_with_a_fixed_title(self):
        text = self._text()
        assert "ISSUE_TITLE: draw.io editor pin is out of date" in text
        assert text.count("gh issue create") == 1
        assert "gh issue edit" in text and "gh issue close" in text


class TestNoLiveFileNamesAPublicDrawioHost:
    @pytest.mark.parametrize(
        ("text", "named"),
        [
            ("https://embed.diagrams.net/?embed=1", True),
            ("src: 'https://viewer.diagrams.net'", True),
            ("href=https://app.diagrams.net/", True),
            ("http://www.draw.io/", True),
            ("embed.diagrams.net", True),
            ("//test.draw.io/x", True),
            ("https://www.drawio.com/doc/faq/self-hosting", True),
            ("//app.drawio.com", True),
            ("the draw.io editor", False),
            ("drawio-desktop release", False),
            ("/drawio/index.html?embed=1&proto=json", False),
            ("https://github.com/jgraph/drawio/releases/download/v1/draw.war", False),
        ],
    )
    def test_the_matcher(self, text, named):
        assert bool(PUBLIC_HOST.search(text)) is named

    def test_the_scan_reads_the_places_it_guards(self):
        names = {p.relative_to(REPO_ROOT).as_posix() for p in _scanned_files()}
        for expected in (
            "apps/network-assessment-web/components/diagrams/DrawioEmbed.tsx",
            "apps/network-assessment-web/components/diagrams/DrawioEmbed.test.tsx",
            "apps/network-assessment-web/middleware.ts",
            "apps/network-assessment-web/next.config.ts",
            "apps/network-assessment-web/lib/drawio-embed.ts",
            "apps/network-assessment-web/lib/drawio-mcp/server.ts",
            "apps/network-assessment-web/Dockerfile",
            "network_assessment/ai_engine/mcp_client/drawio_mcp_client.py",
            "tests/unit/test_drawio_mcp_client.py",
            ".github/workflows/380-drawio-pin-check.yml",
        ):
            assert expected in names, expected
        assert len(names) > 100
        assert not [n for n in names if n.startswith(VENDORED_EDITOR + "/")]

    def test_only_the_vendored_editor_is_skipped(self, tmp_path):
        # A directory called `drawio` anywhere else is scanned like any other.
        assert "drawio" not in SKIPPED_DIRECTORIES
        assert VENDORED_EDITOR == "apps/network-assessment-web/public/drawio"

    def test_no_live_file_names_a_public_draw_io_host(self):
        offenders: list[str] = []
        for path in _scanned_files():
            raw = path.read_bytes()
            if b"\x00" in raw:
                continue
            for number, line in enumerate(
                raw.decode("utf-8", errors="replace").splitlines(), start=1
            ):
                if PUBLIC_HOST.search(line):
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT).as_posix()}:{number}: {line.strip()[:100]}"
                    )
        assert offenders == []


class TestTheWebCspFramesOnlyThisOrigin:
    def test_frame_src_is_self(self):
        text = MIDDLEWARE.read_text(encoding="utf-8")
        match = re.search(r"frame-src ([^;]+);", text)
        assert match, "the middleware CSP has no frame-src"
        assert match.group(1).strip() == "'self'"

    def test_the_csp_names_no_draw_io_host(self):
        assert not PUBLIC_HOST.search(MIDDLEWARE.read_text(encoding="utf-8"))

    def test_the_editor_path_is_outside_the_middleware_matcher(self):
        text = MIDDLEWARE.read_text(encoding="utf-8")
        assert re.search(r"matcher:\s*\[[^\]]*\(\?!api\|drawio/", text), (
            "/drawio/ carries its own CSP (next.config.ts); a second one from the middleware would be enforced too"
        )
