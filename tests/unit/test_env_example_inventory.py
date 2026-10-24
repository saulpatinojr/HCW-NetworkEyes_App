"""`.env.example` lists every setting the code reads (TODO.md T-733, ticket #246).

The root `.env.example` and `apps/cna-web/.env.example` are the operator's inventory of
settings. This test collects every environment variable name the code reads, through
`os.environ` / `os.getenv` in Python and `process.env` in TypeScript, under `cna/`, `apps/`
and `packages/`, and fails with the names that neither file mentions. A commented-out line
counts as a mention, so a secret such as `CREDENTIAL_ENCRYPTION_KEY` can be listed with no value.

It also checks that no secret-named variable (`*_SECRET`, `*_TOKEN`, `*_KEY`) carries a real
value in either file: only blank values and the documented placeholders are allowed.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ("cna", "apps", "packages")
ENV_FILES = (REPO_ROOT / ".env.example", REPO_ROOT / "apps" / "cna-web" / ".env.example")

# Directories that hold dependencies, build output or tests, not the code that runs.
SKIPPED_DIRS = {
    "node_modules",
    ".next",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    "tests",
    "test",
    "e2e",
    "coverage",
}
PYTHON_SUFFIXES = {".py"}
TYPESCRIPT_SUFFIXES = {".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"}
TEST_FILE = re.compile(r"(\.test\.|\.spec\.|(^|/)test_[^/]*\.py$|(^|/)conftest\.py$)")

# Names the platform, the shell or a tool sets; they are not settings an operator provides.
PLATFORM_SET = {
    "PATH",  # the shell
    "HOME",  # the shell
    "NODE_ENV",  # Next.js and the web Dockerfile set it
    "NEXT_RUNTIME",  # Next.js sets it per runtime (edge or nodejs)
    "NEXT_PHASE",  # Next.js sets it while building
    "CI",  # CI systems set it
    "PORT",  # the hosting platform (container runtime) sets it
    "HOSTNAME",  # the container runtime sets it
}

_ENV_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
PYTHON_READS = [
    re.compile(rf"""os\.environ\s*\[\s*["']({_ENV_NAME})["']\s*\]"""),
    re.compile(rf"""os\.environ\.(?:get|pop|setdefault)\(\s*["']({_ENV_NAME})["']"""),
    re.compile(rf"""os\.getenv\(\s*["']({_ENV_NAME})["']"""),
    re.compile(rf"""["']({_ENV_NAME})["']\s+(?:not\s+)?in\s+os\.environ"""),
]
TYPESCRIPT_READS = [
    re.compile(rf"process\.env\.({_ENV_NAME})"),
    re.compile(rf"""process\.env\[\s*["']({_ENV_NAME})["']\s*\]"""),
]

# Placeholder values the files may carry for a secret-named variable.
PLACEHOLDER = re.compile(r"^(change-me[\w-]*|your-[\w-]+|<[^>]*>)$", re.IGNORECASE)
SECRET_NAME = re.compile(r"(_SECRET|_TOKEN|_KEY)$")


def _source_files() -> list[Path]:
    found: list[Path] = []
    for root in SCAN_ROOTS:
        for path in (REPO_ROOT / root).rglob("*"):
            relative = path.relative_to(REPO_ROOT)
            if not path.is_file() or any(part in SKIPPED_DIRS for part in relative.parts):
                continue
            if path.suffix in PYTHON_SUFFIXES | TYPESCRIPT_SUFFIXES and not TEST_FILE.search(
                relative.as_posix()
            ):
                found.append(path)
    return found


def collect_read_names() -> dict[str, set[str]]:
    """Map each environment variable name the code reads to the files that read it."""
    names: dict[str, set[str]] = {}
    for path in _source_files():
        patterns = PYTHON_READS if path.suffix in PYTHON_SUFFIXES else TYPESCRIPT_READS
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in patterns:
            for match in pattern.finditer(text):
                names.setdefault(match.group(1), set()).add(path.relative_to(REPO_ROOT).as_posix())
    return names


def _env_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in ENV_FILES)


def _mentions(text: str, name: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", text) is not None


def test_the_scan_finds_the_settings_the_code_reads():
    # Guards the scanner itself: if the patterns or paths stop matching, the main test
    # would pass with nothing to check.
    names = collect_read_names()
    assert len(names) >= 40
    assert {"CNA_API_TOKEN", "CNA_AI_MODE", "DATABASE_URL"} <= set(names)


def test_every_setting_the_code_reads_is_listed_in_an_env_example():
    text = _env_text()
    missing = {
        name: sorted(files)
        for name, files in collect_read_names().items()
        if name not in PLATFORM_SET and not _mentions(text, name)
    }
    assert not missing, (
        "The code reads these environment variables but neither .env.example nor "
        "apps/cna-web/.env.example mentions them. Add each one (a commented-out line is "
        "enough, and is the right form for a secret) or, if the platform sets it, add it to "
        "PLATFORM_SET with a reason:\n"
        + "\n".join(
            f"  {name}  (read in {', '.join(files)})" for name, files in sorted(missing.items())
        )
    )


def test_no_secret_named_variable_carries_a_real_value():
    offenders: list[str] = []
    for path in ENV_FILES:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, _, rest = stripped.partition("=")
            name = name.strip().removeprefix("export ").strip()
            if not SECRET_NAME.search(name):
                continue
            # Drop a trailing comment and the quotes around the value.
            value = re.split(r"\s+#", rest, maxsplit=1)[0].strip().strip("\"'")
            if value and not PLACEHOLDER.match(value):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number} {name}")
    assert not offenders, (
        "These secret-named variables carry a value other than blank or a documented "
        "placeholder (change-me…, your-…, <…>):\n  " + "\n  ".join(offenders)
    )
