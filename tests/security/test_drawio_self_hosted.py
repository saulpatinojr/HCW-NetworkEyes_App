"""The diagram editor is served by this deployment: customer topology never goes to a public draw.io host.

``REVIEW.md`` R-019 / issue NE-9. The editor on the Diagram page is the draw.io web app, fetched at image build
(stage ``drawio-webapp`` of ``apps/cna-web/Dockerfile``) and served under ``/drawio/`` with a Content-Security-Policy
that lets it talk to nothing but this origin. These checks keep that from coming back:

* ``TestTheEditorIsPinned`` — the release is pinned by version and sha256, the download URL is built from the pinned
  version, and the runner image receives the files.
* ``TestNoLiveFileNamesAPublicDrawioHost`` — no code, configuration or workflow file names a public draw.io or
  diagrams.net host. The web tier has the same check in ``apps/cna-web/lib/drawio-embed.test.ts``, next to the
  CSP and embed-URL assertions.
* ``TestTheWebCspFramesOnlyThisOrigin`` — the application's own CSP has no draw.io host in ``frame-src`` or anywhere.

All three are static reads of files. They do not prove what the running image serves; the build smoke test and the
vitest suite cover the headers, and a browser run is the proof that the editor loads (``CHANGELOG.md``).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
THIS_FILE = Path(__file__).resolve()
DOCKERFILE = REPO_ROOT / "apps" / "cna-web" / "Dockerfile"
MIDDLEWARE = REPO_ROOT / "apps" / "cna-web" / "middleware.ts"

#: A URL, or a well-known bare host such as ``embed.<domain>``, under draw.io's or diagrams.net's domains. The
#: product name written as prose ("the draw.io editor") is not a host and does not match.
PUBLIC_HOST = re.compile(
    r"(?://|\b(?:embed|viewer|app|www|icons|log|test)\.)(?:[a-z0-9-]+\.)*(?:diagrams\.net|draw\.io)(?![a-z0-9-])",
    re.IGNORECASE,
)

#: Where code and configuration live. Documentation, history and the tests are not scanned: they may name a host to
#: explain or to prove a guard (the web tier's own guard is ``apps/cna-web/lib/drawio-embed.test.ts``).
SCANNED_ROOTS = ("apps", "cna", "packages", "scripts", ".github", "infra")
SCANNED_FILES = ("Dockerfile", "docker-compose.yml", "pyproject.toml", ".env.example")
SKIPPED_DIRECTORIES = frozenset(
    {
        "node_modules",
        ".next",
        "__pycache__",
        ".ruff_cache",
        ".pytest_cache",
        ".mypy_cache",
        ".venv",
        "tests",
        "drawio",
    }
)
GUARD_FILES = frozenset({"apps/cna-web/lib/drawio-embed.test.ts"})
MAX_BYTES = 2_000_000

VERSION = re.compile(r"^\d+\.\d+\.\d+$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _stage(text: str, name: str) -> str:
    """The instructions of one build stage, from its FROM line to the next FROM."""
    match = re.search(
        rf"^FROM\s+\S+\s+AS\s+{re.escape(name)}\s*$(.*?)(?=^FROM\s|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"{DOCKERFILE.name} has no stage named {name}"
    return match.group(1)


def _scanned_files() -> list[Path]:
    files: list[Path] = [REPO_ROOT / name for name in SCANNED_FILES if (REPO_ROOT / name).is_file()]
    for root in SCANNED_ROOTS:
        base = REPO_ROOT / root
        for directory, subdirectories, names in os.walk(base):
            subdirectories[:] = sorted(d for d in subdirectories if d not in SKIPPED_DIRECTORIES)
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
    def test_the_pin_is_a_version_and_a_sha256(self):
        stage = _stage(DOCKERFILE.read_text(encoding="utf-8"), "drawio-webapp")
        version = re.search(r"^ARG DRAWIO_WEBAPP_VERSION=(\S+)\s*$", stage, re.MULTILINE)
        digest = re.search(r"^ARG DRAWIO_WEBAPP_SHA256=(\S+)\s*$", stage, re.MULTILINE)
        assert version and VERSION.fullmatch(version.group(1)), (
            "DRAWIO_WEBAPP_VERSION must be an exact x.y.z"
        )
        assert digest and SHA256.fullmatch(digest.group(1)), (
            "DRAWIO_WEBAPP_SHA256 must be 64 lowercase hex digits"
        )

    def test_the_download_uses_the_pinned_version_and_is_verified_before_use(self):
        stage = _stage(DOCKERFILE.read_text(encoding="utf-8"), "drawio-webapp")
        assert (
            "https://github.com/jgraph/drawio/releases/download/v${DRAWIO_WEBAPP_VERSION}/draw.war"
            in stage
        )
        download = stage.index("RUN wget ")
        check = stage.index('/tmp/draw.war" | sha256sum -c -')
        unzip = stage.index("&& unzip -q")
        assert '"${DRAWIO_WEBAPP_SHA256}  /tmp/draw.war"' in stage
        assert download < check < unzip, (
            "the checksum must be checked after the download and before the unzip"
        )

    def test_the_server_side_of_the_war_never_reaches_the_image(self):
        stage = _stage(DOCKERFILE.read_text(encoding="utf-8"), "drawio-webapp")
        assert "WEB-INF" in stage and "rm -rf" in stage, (
            "the Java and OAuth side of the war must be deleted"
        )

    def test_the_licence_travels_with_the_files(self):
        stage = _stage(DOCKERFILE.read_text(encoding="utf-8"), "drawio-webapp")
        assert "COPY third-party/drawio/LICENSE /out/LICENSE" in stage
        licence = REPO_ROOT / "apps" / "cna-web" / "third-party" / "drawio" / "LICENSE"
        assert "Apache License" in licence.read_text(encoding="utf-8")[:200]

    def test_the_runner_image_serves_the_editor_from_its_own_files(self):
        runner = _stage(DOCKERFILE.read_text(encoding="utf-8"), "runner")
        assert "COPY --from=drawio-webapp --chown=nextjs:nodejs /out ./app/public/drawio" in runner

    def test_the_downloaded_files_are_not_committed(self):
        ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        assert "apps/cna-web/public/drawio/" in ignored
        dockerignore = (
            (REPO_ROOT / "apps" / "cna-web" / ".dockerignore")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        assert "public/drawio" in dockerignore


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
            "apps/cna-web/components/diagrams/DrawioEmbed.tsx",
            "apps/cna-web/middleware.ts",
            "apps/cna-web/next.config.ts",
            "apps/cna-web/lib/drawio-embed.ts",
            "apps/cna-web/lib/drawio-mcp/server.ts",
            "apps/cna-web/Dockerfile",
            "cna/ai_engine/mcp_client/drawio_mcp_client.py",
        ):
            assert expected in names, expected
        assert len(names) > 100

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
