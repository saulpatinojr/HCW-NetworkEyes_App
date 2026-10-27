"""NetworkEyes is a free tool: the words that read like a paid service or name another company stay out (ticket #318).

Owner wording rule (2026-10-26): NetworkEyes is a free tool for followers of Hybrid Cloud Works, shared through
GitHub, with no paid edition. Docker's free open-source programme refuses a project that makes a profit "through
services or by charging for higher tiers" (https://www.docker.com/community/open-source/application/), and a reviewer
is likely to read the README, the documents, the Dockerfile and the image labels. (Docker's page says nothing about
naming another company; that part is the owner's rule.) These tests keep the wording that ticket #318 removed from
coming back. They read tracked files only, so they prove what the repository says and nothing about a
running system or a published image.

* ``CBTS`` (a company) is named in no tracked file, in no file name and in no code name, except the history files
  and the guard files below. The owner chose the Hybrid Cloud Works logo for the report cover and the web pages
  (ticket #318, 2026-10-26), so ``BRAND_ASSETS`` and ``BRAND_FILE_NAMES``, which held the company's logo and palette
  while that was open, are empty. They stay as the way to excuse a line, and a test fails when an entry excuses
  nothing, so a list can only shrink.
* The Hybrid Cloud Works logo files exist, are small PNGs with a transparent background, and are the files the web
  header, the sign-in page, the report cover and the encyclopedia cover name.
* The documents (every Markdown file, ``NOTICE``, ``.env.example`` and everything under ``.github/``) say "user", not
  "customer", and "build", not "edition", except for the quotes in ``DOC_EXCEPTIONS``.
* Dockerfile comments and every ``LABEL`` say none of those words, and no file is named after the company.
* The text sent to an AI model names no company and no payment. (``report-prompts.test.ts`` covers the report
  sections; the files below cover the older prompt path, the report title block and the chat copilot.)

Code names are not wording and stay: ``clientOrg``, the report types ``condensed`` and ``expanded``, the Dockerfile
argument ``EDITION``, ``NETWORK_ASSESSMENT_EDITION``, the module ``edition.py`` and the JSON key ``edition``.
"""

from __future__ import annotations

import re
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# The guard reads the list of tracked files from git. The `network-assessment-test` service in docker-compose.yml builds from a
# context without `.git`, where there is nothing to list; skip there instead of raising. A worktree has `.git` as a
# file, so the check is `exists()`, not `is_dir()`. In CI the checkout has `.git`, and
# `test_the_scan_reads_the_places_it_guards` fails loudly if the list ever comes back empty.
if shutil.which("git") is None or not (REPO_ROOT / ".git").exists():
    pytest.skip("needs a git checkout and the git program", allow_module_level=True)
THIS_FILE = "tests/unit/test_free_tool_wording.py"

#: History is never rewritten.
HISTORY_FILES = frozenset({"CHANGELOG.md"})
#: Files that spell the words out on purpose, to prove a guard. Each is itself a guard.
GUARD_FILES = frozenset(
    {
        THIS_FILE,
        "tests/security/test_standalone_boundary.py",  # names the other owner's GitHub account
        "apps/network-assessment-web/lib/standalone-boundary.test.ts",  # the same, for the web tier
        "apps/network-assessment-web/lib/report-prompts.test.ts",  # the banned-word list of the report prompts
        "apps/network-assessment-web/lib/logo-url.test.ts",  # spells out the company hosts to prove the logo allow-list rejects them
    }
)
LOCK_FILES = frozenset({"uv.lock", "package-lock.json"})
MAX_BYTES = 2_000_000

#: Any spelling of the company name, inside a longer word as well (``cbts.com``, ``CBTS_NAVY``, ``cbts-logo``).
CBTS = re.compile(r"cbts", re.IGNORECASE)

#: (file, pattern, reason): lines that may still name the company. EMPTY: the owner chose the Hybrid Cloud Works logo
#: (ticket #318, 2026-10-26) and the colour constants and comments were renamed with their values unchanged. An entry
#: excuses the text it matches and nothing else: the matched text is cut out of the line, and the line is excused only
#: if no company name is left. Remove an entry as soon as it excuses no line
#: (``test_every_brand_asset_entry_is_still_needed`` fails until you do).
BRAND_ASSETS: tuple[tuple[str, re.Pattern[str], str], ...] = ()
#: File names that may carry the company name. Empty for the same reason.
BRAND_FILE_NAMES: frozenset[str] = frozenset()

#: The Hybrid Cloud Works logo, made from the owner's logo (HCW-HybridCloudWorks, frontend/public/icons/hcw-logo.png):
#: black strokes for a light background, white strokes for a dark one, both on a transparent background.
LOGO_BLACK = "apps/network-assessment-web/public/hcw-logo-black.png"
LOGO_WHITE = "apps/network-assessment-web/public/hcw-logo-white.png"
#: The encyclopedia cover is dark navy, so it carries the white-stroke logo, at the size WeasyPrint needs for print.
LOGO_COVER = "network_assessment/report_engine/templates/assets/logos/hcw-logo-cover.png"
WEB_PAGES_WITH_THE_LOGO = (
    "apps/network-assessment-web/app/(dashboard)/layout.tsx",
    "apps/network-assessment-web/app/auth/signin/page.tsx",
    "apps/network-assessment-web/app/(dashboard)/engagements/[id]/report/page.tsx",
)
MAX_LOGO_BYTES = 100_000

#: Rules for the documents (Markdown files and the issue forms). Matching is case-insensitive.
DOC_RULES: dict[str, re.Pattern[str]] = {
    "customer": re.compile(r"\bcustomers?\b", re.IGNORECASE),
    "appliance, lab or downstream edition": re.compile(
        r"\b(?:appliance|lab|downstream)\s+editions?\b", re.IGNORECASE
    ),
    "client-facing, client delivery or client engagement": re.compile(
        r"\bclient[- ](?:facing|delivery|engagements?)\b", re.IGNORECASE
    ),
}

#: (file, pattern, reason). The text an entry matches is cut out of a line before the rules are applied, so an entry
#: excuses that text and nothing else on the line. Every entry must excuse something
#: (``test_every_document_exception_still_matches``).
DOC_EXCEPTIONS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "REVIEW.md",
        re.compile(r"customer[- ]facing[- ]appliance[- ]repository[- ]names"),
        "R-015 was withdrawn on 2026-10-25; it is dated history about another owner's repositories",
    ),
    (
        "REVIEW.md",
        re.compile(r"customer-like beta acceptance|cannot be offered to a client engagement"),
        "R-008 is history: it left this repository on 2026-09-15",
    ),
    (
        "TODO.md",
        re.compile(r"VPN/customer gateways"),
        "AWS calls its VPN endpoint on the user's side a customer gateway",
    ),
    (
        "REFACTOR_APP.md",
        re.compile(r"(?:appliance|lab) edition:"),
        "quotes a startup message the code prints; tests pin the message",
    ),
    (
        "REFACTOR_APP.md",
        re.compile(r'"lab edition"'),
        "quotes a message the code prints; tests pin the message",
    ),
    (
        "TODO.md",
        re.compile(r"lab edition: boundary holds"),
        "quotes a message the code prints; tests pin the message",
    ),
)

#: The files whose text goes to an AI model or into the title block of a report. Identifiers such as ``clientOrg``
#: and ``customerLogoUrl`` do not match because the pattern needs a word boundary after the word.
MODEL_FACING_FILES = (
    "apps/network-assessment-web/lib/openai.ts",
    "apps/network-assessment-web/lib/report-orchestrator.ts",
)
MODEL_FACING_BANNED = re.compile(
    r"\b(?:cbts|paid|paying|payments?|pays?|fees?|consult\w*|customers?|malpractice)\b"
    # "client" as a buyer or a person. A variable called ``client`` (an SDK client) is code and is not matched.
    r"|\bclient (?:deliverable|engagement|delivery|confidential|organi[sz]ation)\b"
    r"|\b(?:the|a|for|with|to) client\b"
    r"|\*\*client\b|(?-i:\bClient:)",
    re.IGNORECASE,
)

#: Words that must not appear in a Dockerfile comment or in an image label. The build argument ``EDITION`` is upper
#: case, so only the capitalised or lower-case word ``edition`` is matched, not the name of the argument.
#: A comment may say "client" for a software client (the Prisma client); a label never should.
_WORDS = r"cbts|paid|pricing|customers?|enterprise|consult\w*"
DOCKERFILE_COMMENT_BANNED = re.compile(rf"\b[Ee]ditions?\b|(?i:\b(?:{_WORDS})\b)")
IMAGE_LABEL_BANNED = re.compile(rf"(?i)\b(?:editions?|clients?|{_WORDS})\b")


def _tracked() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"], capture_output=True, check=True
    ).stdout
    return sorted(name for name in out.decode("utf-8").split("\0") if name)


def _text(relative: str) -> str | None:
    path = REPO_ROOT / relative
    if path.name in LOCK_FILES or not path.is_file() or path.stat().st_size > MAX_BYTES:
        return None
    raw = path.read_bytes()
    if b"\x00" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _png_header(relative: str) -> tuple[int, int, int]:
    """(width, height, colour type) of a PNG, read from its header; fails if the file is not a PNG."""
    raw = (REPO_ROOT / relative).read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", f"{relative} is not a PNG file"
    width, height = struct.unpack(">II", raw[16:24])
    return width, height, raw[25]


def _documents() -> list[str]:
    """Every Markdown file, the notices, the settings inventory and everything GitHub shows from ``.github/``."""
    return [
        name
        for name in _tracked()
        if name not in HISTORY_FILES
        and (
            name.endswith(".md")
            or name in {"NOTICE", ".env.example"}
            or name.startswith(".github/")
        )
    ]


def _instructions(dockerfile: str) -> list[str]:
    """The Dockerfile instructions, with continuation lines joined and comment lines dropped."""
    logical: list[str] = []
    current = ""
    for raw in dockerfile.splitlines():
        line = raw.strip()
        if line.startswith("#") or (not line and not current):
            continue
        if line.endswith("\\"):
            current += line[:-1] + " "
            continue
        logical.append((current + line).strip())
        current = ""
    if current:
        logical.append(current.strip())
    return logical


def _broken_rules(line: str) -> list[str]:
    return [name for name, pattern in DOC_RULES.items() if pattern.search(line)]


def _unexcused_rules(relative: str, line: str) -> list[str]:
    """The rules a line still breaks after the text its file's DOC_EXCEPTIONS excuse is cut out."""
    for file, pattern, _reason in DOC_EXCEPTIONS:
        if file == relative:
            line = pattern.sub("", line)
    return _broken_rules(line)


def _names_the_company_unexcused(relative: str, line: str) -> bool:
    """True when the line names the company after the text its file's BRAND_ASSETS excuse is cut out."""
    for file, pattern, _reason in BRAND_ASSETS:
        if file == relative:
            line = pattern.sub("", line)
    return bool(CBTS.search(line))


class TestTheCompanyNameStaysOut:
    def test_the_scan_reads_the_places_it_guards(self) -> None:
        # A guard whose file list silently came back empty would pass for the wrong reason.
        tracked = set(_tracked())
        for expected in (
            "README.md",
            "CLAUDE.md",
            "NOTICE",
            ".env.example",
            ".github/SECURITY.md",
            ".github/ISSUE_TEMPLATE/bug_report.yml",
            "Dockerfile",
            "apps/network-assessment-web/lib/openai.ts",
            "apps/network-assessment-web/lib/report-prompts.ts",
            "network_assessment/ai_engine/chat_agent.py",
            *(file for file, _pattern, _reason in BRAND_ASSETS),
        ):
            assert expected in tracked, f"{expected} is not a tracked file; update this guard"

    def test_no_tracked_file_names_the_company_outside_the_brand_asset_list(self) -> None:
        offenders: list[str] = []
        for relative in _tracked():
            if relative in HISTORY_FILES or relative in GUARD_FILES:
                continue
            text = _text(relative)
            if text is None:
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if _names_the_company_unexcused(relative, line):
                    offenders.append(f"{relative}:{number}: {line.strip()[:100]}")
        assert not offenders, (
            "NetworkEyes is a free tool and names no company. Reword these lines (a brand asset that has to stay "
            "goes in BRAND_ASSETS with the reason):\n" + "\n".join(offenders)
        )

    def test_every_brand_asset_entry_is_still_needed(self) -> None:
        stale = [
            f"{file}: {pattern.pattern}"
            for file, pattern, _reason in BRAND_ASSETS
            if not any(
                CBTS.search(line) and pattern.search(line)
                for line in (_text(file) or "").splitlines()
            )
        ]
        assert not stale, (
            f"these BRAND_ASSETS entries excuse no line any more; delete them: {stale}"
        )

    def test_no_file_is_named_after_the_company_outside_the_logo_list(self) -> None:
        tracked = set(_tracked())
        named = {name for name in tracked if CBTS.search(name)}
        assert named == BRAND_FILE_NAMES, (
            "a file name that carries the company name must be in BRAND_FILE_NAMES (the logo files), and "
            f"a name whose file is gone must leave it. Unlisted: {sorted(named - BRAND_FILE_NAMES)}; "
            f"listed but gone: {sorted(BRAND_FILE_NAMES - named)}"
        )

    @pytest.mark.parametrize(
        "text",
        [
            "CBTS",
            "cbts.com",
            "my-cbtssandbox-env",
            "CBTSSandbox",
            "someone@cbts.example",
            "/cbts-logo-dark-teal.svg",
            "CBTS_NAVY",
            "saulpatino-cbts/x",
            "Cbts",
        ],
    )
    def test_the_pattern_catches_every_spelling(self, text: str) -> None:
        assert CBTS.search(text)

    @pytest.mark.parametrize(
        "text", ["Hybrid Cloud Works", "NetworkEyes", "Cloud Network Assessment"]
    )
    def test_the_pattern_lets_other_words_through(self, text: str) -> None:
        assert not CBTS.search(text)


class TestTheHybridCloudWorksLogo:
    """The owner chose the Hybrid Cloud Works logo (ticket #318); these tests keep the pages and files in step."""

    def test_the_logo_files_are_tracked_small_pngs_with_a_transparent_background(self) -> None:
        tracked = set(_tracked())
        for relative in (LOGO_BLACK, LOGO_WHITE, LOGO_COVER):
            assert relative in tracked, f"{relative} is not a tracked file"
            width, height, colour_type = _png_header(relative)
            assert colour_type in (4, 6), (
                f"{relative} has no alpha channel (colour type {colour_type})"
            )
            assert 300 <= width <= 1000 and 300 <= height <= 1000, f"{relative} is {width}x{height}"
            assert (REPO_ROOT / relative).stat().st_size <= MAX_LOGO_BYTES, (
                f"{relative} is larger than the limit"
            )

    def test_the_web_logos_are_big_enough_for_the_largest_use_and_the_cover_logo_for_print(
        self,
    ) -> None:
        # Largest web use: the report page cover, 160 css pixels wide, on a screen with a 2x pixel ratio.
        for relative in (LOGO_BLACK, LOGO_WHITE):
            assert _png_header(relative)[0] >= 320
        # The encyclopedia cover logo is 4 cm wide: 300 dpi needs 472 pixels.
        assert _png_header(LOGO_COVER)[0] >= 472

    @pytest.mark.parametrize("relative", WEB_PAGES_WITH_THE_LOGO)
    def test_each_web_page_uses_the_black_logo_on_light_and_the_white_logo_on_dark(
        self, relative: str
    ) -> None:
        text = _text(relative) or ""
        assert "/hcw-logo-black.png" in text and "/hcw-logo-white.png" in text, relative
        if relative.endswith("report/page.tsx"):
            assert re.search(r'src="/hcw-logo-black\.png"[^>]*dark:hidden', text)
            assert re.search(r'src="/hcw-logo-white\.png"[^>]*hidden dark:block', text)
        else:
            # <picture>: the white logo is the dark-scheme source, the black logo is the default image.
            assert re.search(
                r'<source\s+srcSet="/hcw-logo-white\.png"\s+media="\(prefers-color-scheme: dark\)"',
                text,
            )
            assert re.search(r'<img\s+src="/hcw-logo-black\.png"', text)

    def test_every_image_path_the_web_pages_name_is_a_file_in_public(self) -> None:
        for relative in WEB_PAGES_WITH_THE_LOGO:
            for match in re.finditer(
                r"""["'](/[A-Za-z0-9_.-]+\.(?:png|svg|jpe?g|webp|ico))["']""", _text(relative) or ""
            ):
                target = (
                    REPO_ROOT / "apps/network-assessment-web/public" / match.group(1).lstrip("/")
                )
                assert target.is_file(), (
                    f"{relative} names {match.group(1)}, which is not in apps/network-assessment-web/public"
                )

    def test_the_encyclopedia_html_embeds_the_cover_logo_so_it_shows_in_a_browser_and_in_the_pdf(
        self,
    ) -> None:
        # The HTML is opened by WeasyPrint and also served at /api/deliverables/<id>, where a relative address such as
        # "assets/logos/..." points at a page that does not exist. A data: URI works in both places.
        import base64

        from network_assessment.report_engine.encyclopedia_report import EncyclopediaReportRenderer

        html = EncyclopediaReportRenderer(edition="condensed").render_html(
            [],
            engagement={
                "engagement_id": "eng-logo-001",
                "client_org": "Example Org",
                "engagement_name": "Example Assessment",
            },
        )
        match = re.search(r'<img class="logo" src="([^"]+)" alt="([^"]*)"', html)
        assert match, "the cover has no logo image"
        source, alt = match.groups()
        assert alt == "Hybrid Cloud Works"
        prefix = "data:image/png;base64,"
        assert source.startswith(prefix), f"the cover logo is not embedded: {source[:60]}"
        assert base64.b64decode(source[len(prefix) :]) == (REPO_ROOT / LOGO_COVER).read_bytes()

    def test_a_templates_folder_without_the_logo_falls_back_to_the_relative_address(
        self, tmp_path: Path
    ) -> None:
        from network_assessment.report_engine.encyclopedia_report import (
            _TEMPLATES_DIR,
            EncyclopediaReportRenderer,
        )

        copy = tmp_path / "templates"
        shutil.copytree(_TEMPLATES_DIR, copy, ignore=shutil.ignore_patterns("hcw-logo-cover.png"))
        html = EncyclopediaReportRenderer(templates_dir=copy, edition="condensed").render_html(
            [], engagement={"engagement_id": "eng-logo-002", "engagement_name": "Example"}
        )
        assert 'src="assets/logos/hcw-logo-cover.png"' in html

    def test_the_cover_logo_file_is_where_weasyprint_looks_for_it(self) -> None:
        # render() gives WeasyPrint base_url=_TEMPLATES_DIR, so the relative address resolves to this file.
        from network_assessment.report_engine.encyclopedia_report import _COVER_LOGO, _TEMPLATES_DIR

        assert (REPO_ROOT / LOGO_COVER).samefile(_TEMPLATES_DIR / _COVER_LOGO)

    def test_the_logo_pixels_are_the_colour_the_file_name_says_on_a_transparent_background(
        self,
    ) -> None:
        image_module = pytest.importorskip("PIL.Image")
        for relative, stroke in ((LOGO_BLACK, 0), (LOGO_WHITE, 255), (LOGO_COVER, 255)):
            with image_module.open(REPO_ROOT / relative) as image:
                width, height = image.size
                data = image.convert("LA").tobytes()  # grey, alpha, grey, alpha, ...
            greys, alphas = data[0::2], data[1::2]
            for x, y in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
                assert alphas[y * width + x] == 0, (
                    f"{relative}: the corner ({x}, {y}) is not transparent"
                )
            inked = [grey for grey, alpha in zip(greys, alphas, strict=True) if alpha > 128]
            assert len(inked) / (width * height) > 0.03, f"{relative} has almost no strokes"
            assert all(abs(grey - stroke) <= 8 for grey in inked), (
                f"{relative}: its strokes are not {'white' if stroke else 'black'}"
            )

    def test_the_cover_is_dark_so_it_needs_the_light_stroke_logo(self) -> None:
        css = (
            REPO_ROOT / "network_assessment/report_engine/templates/encyclopedia/encyclopedia.css"
        ).read_text("utf-8")
        assert re.search(r"@page cover \{\s*background: #012638;", css), (
            "the cover page is no longer dark navy"
        )


class TestTheDocumentsSayUserAndBuild:
    def test_no_document_breaks_a_rule_outside_the_listed_quotes(self) -> None:
        offenders: list[str] = []
        for relative in _documents():
            text = _text(relative) or ""
            for number, line in enumerate(text.splitlines(), start=1):
                broken = _unexcused_rules(relative, line)
                if broken:
                    offenders.append(
                        f"{relative}:{number} [{', '.join(broken)}]: {line.strip()[:100]}"
                    )
        assert not offenders, (
            "Say 'user' for the people and 'build' for a version of the product (a quote of a message the code prints "
            "or a dated history line goes in DOC_EXCEPTIONS with its reason):\n"
            + "\n".join(offenders)
        )

    def test_every_document_exception_still_matches(self) -> None:
        unused: list[str] = []
        for file, pattern, _reason in DOC_EXCEPTIONS:
            text = _text(file) or ""
            if not any(_broken_rules(line) and pattern.search(line) for line in text.splitlines()):
                unused.append(f"{file}: {pattern.pattern}")
        assert not unused, f"these DOC_EXCEPTIONS excuse no line any more; delete them: {unused}"

    @pytest.mark.parametrize(
        ("line", "broken"),
        [
            ("Never put customer data in an issue.", ["customer"]),
            ("Customers grant a write role.", ["customer"]),
            ("the free lab edition", ["appliance, lab or downstream edition"]),
            ("The appliance edition serves two APIs.", ["appliance, lab or downstream edition"]),
            ("a downstream  edition", ["appliance, lab or downstream edition"]),
            (
                "acceptable for a client-facing delivery portal.",
                ["client-facing, client delivery or client engagement"],
            ),
            (
                "the client delivery portal",
                ["client-facing, client delivery or client engagement"],
            ),
            (
                "cannot be offered to a client engagement",
                ["client-facing, client delivery or client engagement"],
            ),
        ],
    )
    def test_the_rules_catch_the_old_wording(self, line: str, broken: list[str]) -> None:
        assert _broken_rules(line) == broken

    @pytest.mark.parametrize(
        "line",
        [
            "the lab build and the appliance build",
            "There is no paid edition.",
            "ARG EDITION=appliance",
            "NETWORK_ASSESSMENT_EDITION=lab and edition.py",
            "`customerLogoUrl` and `clientOrg` are code names",
            "the client secret and APP_CLIENT_ID are technical terms",
            "Users pull the images.",
        ],
    )
    def test_the_rules_let_code_names_and_technical_terms_through(self, line: str) -> None:
        assert _broken_rules(line) == []


class TestDockerfilesAndPrompts:
    def test_dockerfile_comments_and_image_labels_use_the_free_tool_wording(self) -> None:
        offenders: list[str] = []
        dockerfiles = [
            name for name in _tracked() if name == "Dockerfile" or name.endswith("/Dockerfile")
        ]
        assert dockerfiles, "no Dockerfile is tracked"
        for relative in dockerfiles:
            text = _text(relative) or ""
            for number, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("#") and DOCKERFILE_COMMENT_BANNED.search(stripped):
                    offenders.append(f"{relative}:{number}: {stripped[:100]}")
            for instruction in _instructions(text):
                if instruction.upper().startswith("LABEL ") and IMAGE_LABEL_BANNED.search(
                    instruction
                ):
                    offenders.append(f"{relative}: {instruction[:100]}")
        assert not offenders, "\n".join(offenders)

    def test_every_image_label_of_the_root_dockerfile_was_read(self) -> None:
        # The label check must see the real LABEL instruction (it spans five lines), not an empty list.
        labels = [
            i for i in _instructions(_text("Dockerfile") or "") if i.upper().startswith("LABEL ")
        ]
        assert any("org.opencontainers.image.licenses" in label for label in labels)

    def test_continuation_lines_are_joined_and_comments_dropped(self) -> None:
        text = 'FROM x\n# a comment\nLABEL a="1" \\\n  b="2" \\\n  # inner comment\n  c="3"\nRUN true\n'
        assert _instructions(text) == ["FROM x", 'LABEL a="1"  b="2"  c="3"', "RUN true"]

    @pytest.mark.parametrize(
        "instruction",
        [
            'LABEL vendor="Acme Consulting"',
            'LABEL org.opencontainers.image.title="NetworkEyes Enterprise"',
            'LABEL com.example.edition="Pro"',
            'LABEL maintainer="CBTS"',
            'LABEL org.opencontainers.image.description="a paid service for clients"',
        ],
    )
    def test_the_label_pattern_catches_what_a_reviewer_would_object_to(
        self, instruction: str
    ) -> None:
        assert IMAGE_LABEL_BANNED.search(instruction)

    def test_the_label_pattern_lets_the_real_labels_through(self) -> None:
        label = (
            'LABEL org.opencontainers.image.title="NetworkEyes" '
            'org.opencontainers.image.description="Cloud Network Assessment CLI" '
            'org.opencontainers.image.licenses="Apache-2.0"'
        )
        assert not IMAGE_LABEL_BANNED.search(label)

    @pytest.mark.parametrize(
        "comment",
        [
            "# Two editions from one file",
            "# The appliance edition serves both clouds",
            "# Edition guard",
            "# so that no customer topology leaves the deployment",
            "# Customers pull this image",
            "# CBTS palette",
            "# Enterprise tier",
        ],
    )
    def test_the_comment_pattern_catches_the_old_comments(self, comment: str) -> None:
        assert DOCKERFILE_COMMENT_BANNED.search(comment)

    @pytest.mark.parametrize(
        "comment",
        [
            "# Two builds from one file",
            "ARG EDITION=appliance",
            "# `--build-arg EDITION=lab` selects the lab target",
            "# the Prisma client is generated from the schema",
        ],
    )
    def test_the_comment_pattern_lets_the_build_argument_through(self, comment: str) -> None:
        assert not DOCKERFILE_COMMENT_BANNED.search(comment)

    def test_the_text_sent_to_a_model_or_printed_on_a_report_names_no_company_and_no_payment(
        self,
    ) -> None:
        offenders: list[str] = []
        for relative in MODEL_FACING_FILES:
            text = _text(relative)
            assert text, f"{relative} is missing or empty"
            for number, line in enumerate(text.splitlines(), start=1):
                if line.lstrip().startswith(("import ", "} from ")):
                    continue  # module names such as "@prisma/client" are code, not wording
                if MODEL_FACING_BANNED.search(line):
                    offenders.append(f"{relative}:{number}: {line.strip()[:100]}")
        assert not offenders, "\n".join(offenders)

    @pytest.mark.parametrize(
        "line",
        [
            "You are a senior CBTS cloud network security consultant generating a professional client deliverable.",
            "Include a professional header: Client, Engagement, Prepared By: CBTS Cloud Security Practice.",
            "`**Classification:** Client Confidential`",
            "for a CBTS customer engagement.",
            "`**Client:** ${ctx.clientOrg}  `,",
            "parts.push(`Client Organization: ${ctx.clientOrg}`);",
            "Confirm with the client whether this domain is in scope",
        ],
    )
    def test_the_prompt_pattern_catches_the_old_prompts(self, line: str) -> None:
        assert MODEL_FACING_BANNED.search(line)

    @pytest.mark.parametrize(
        "line",
        [
            "clientOrg: string; customerLogoUrl?: string | null;",
            "const client = new OpenAI({ apiKey });",
            "await client.chat.completions.create({ model });",
            "parts.push(`Organization: ${ctx.clientOrg}`);",
        ],
    )
    def test_the_prompt_pattern_lets_code_through(self, line: str) -> None:
        assert not MODEL_FACING_BANNED.search(line)

    def test_the_copilot_prompt_names_no_company_and_no_payment(self) -> None:
        from network_assessment.ai_engine import chat_agent

        prompt = chat_agent._SYSTEM_PROMPT
        assert prompt.startswith("You are the Cloud Network Assessment copilot")
        assert not MODEL_FACING_BANNED.search(prompt)
