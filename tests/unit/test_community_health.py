"""The GitHub community-health files exist and are well formed (ticket #247).

GitHub reads `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `PULL_REQUEST_TEMPLATE.md` and
`ISSUE_TEMPLATE/*` from `.github/`. They live there, not at the root, because the documentation model
(`scripts/validate_documentation_model.py`) allows exactly seven root documents.

The issue forms are YAML, so a typo does not fail anything until someone opens the "New issue" page. These
tests parse each form and check the parts GitHub rejects or silently ignores: unique ids, a label on every
field, dropdown options that are non-empty and unique, and the dropdown values that must match the project
board's options exactly.
"""

import json
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GITHUB = REPO_ROOT / ".github"
FORMS = GITHUB / "ISSUE_TEMPLATE"

COMMUNITY_DOCUMENTS = (
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "PULL_REQUEST_TEMPLATE.md",
)
ISSUE_FORMS = ("bug_report.yml", "feature_request.yml", "work_item.yml")

# Field types GitHub's issue-form schema accepts, and the ones that take answers.
FORM_FIELD_TYPES = {"markdown", "input", "textarea", "dropdown", "checkboxes", "upload"}
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

# The components an issue can be about. Bug reports and feature requests must offer the same list.
COMPONENTS = [
    "Web app (apps/network-assessment-web)",
    "API (apps/network-assessment-api)",
    "Worker (apps/network-assessment-worker)",
    "CLI and analysis engine (network_assessment package)",
    "Azure network engine package (packages/cna-azure-network-engine)",
    "Container images and the image build",
    "CI and repository policy (.github)",
    "Documentation",
    "Not sure",
]


def load_form(name: str) -> dict:
    return yaml.safe_load((FORMS / name).read_text(encoding="utf-8"))


def fields(form: dict) -> list[dict]:
    return form["body"]


def field_by_id(form: dict, field_id: str) -> dict:
    matches = [f for f in fields(form) if f.get("id") == field_id]
    assert len(matches) == 1, f"expected exactly one field with id {field_id!r}"
    return matches[0]


def board_options() -> dict[str, list[str]]:
    """The project board's single-select options, read from the workflow that creates the fields."""
    text = (GITHUB / "workflows" / "390-repository-admin.yml").read_text(encoding="utf-8")
    options: dict[str, list[str]] = {}
    for match in re.finditer(
        r'\{"name":"[^"]+","type":"SINGLE_SELECT","options":\[[^\]]*\]\}', text
    ):
        entry = json.loads(match.group(0))
        options[entry["name"]] = entry["options"]
    return options


# --- the files exist, and only where GitHub reads them ---


@pytest.mark.parametrize("name", COMMUNITY_DOCUMENTS)
def test_community_document_exists_under_dot_github_and_not_at_the_root(name: str) -> None:
    path = GITHUB / name
    assert path.is_file(), f".github/{name} is missing"
    assert path.read_text(encoding="utf-8").strip(), f".github/{name} is empty"
    assert not (REPO_ROOT / name).exists(), (
        f"{name} at the root would break the documentation model"
    )


@pytest.mark.parametrize("name", (*ISSUE_FORMS, "config.yml"))
def test_issue_template_files_exist(name: str) -> None:
    assert (FORMS / name).is_file()


def test_no_markdown_issue_templates_remain() -> None:
    """The task is forms, not markdown templates: a .md template has no required fields."""
    assert sorted(p.name for p in FORMS.glob("*.md")) == []


# --- security policy ---


def test_security_policy_names_the_private_route_and_the_scope() -> None:
    text = (GITHUB / "SECURITY.md").read_text(encoding="utf-8")
    assert "https://github.com/saulpatinojr/HCW-NetworkEyes_App/security/advisories/new" in text
    for heading in ("## Reporting a vulnerability", "## Supported versions"):
        assert heading in text
    assert "public issue" in text


def test_security_policy_does_not_invent_a_contact_address() -> None:
    """The private route is GitHub's form; an address nobody confirmed would send reports nowhere."""
    for name in COMMUNITY_DOCUMENTS:
        text = (GITHUB / name).read_text(encoding="utf-8")
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text), (
            f"{name} contains an e-mail address"
        )


@pytest.mark.parametrize("name", ("SECURITY.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md"))
def test_repository_paths_named_in_the_guides_exist(name: str) -> None:
    """A guide that points at a file or script that is gone misleads the next contributor."""
    text = (GITHUB / name).read_text(encoding="utf-8")
    roots = ("scripts/", ".github/", "apps/", "packages/", "tests/")
    checked = 0
    for token in re.findall(r"`([^`\n]+)`", text):
        if not token.startswith(roots) or any(c in token for c in "*<> "):
            continue
        # `bash scripts/...` style commands are excluded by the space check above; here are bare paths.
        assert (REPO_ROOT / token.rstrip("/")).exists(), (
            f"{name} mentions `{token}`, which does not exist"
        )
        checked += 1
    assert checked, f"{name} names no repository path, so this test would prove nothing"


def test_contributing_guide_commands_point_at_real_scripts() -> None:
    text = (GITHUB / "CONTRIBUTING.md").read_text(encoding="utf-8")
    for script in re.findall(r"(?:bash|python) (scripts/[\w./-]+)", text):
        assert (REPO_ROOT / script).is_file(), (
            f"CONTRIBUTING.md runs {script}, which does not exist"
        )
    assert "scripts/ci/local-container-checks.sh" in text


# --- issue forms ---


@pytest.mark.parametrize("name", ISSUE_FORMS)
def test_issue_form_has_the_keys_github_requires(name: str) -> None:
    form = load_form(name)
    for key in ("name", "description", "body"):
        assert form.get(key), f"{name}: missing {key}"
    assert isinstance(form["body"], list) and form["body"]
    assert "product:networkeyes" in form.get("labels", []), f"{name}: forms carry the product label"


@pytest.mark.parametrize("name", ISSUE_FORMS)
def test_issue_form_fields_are_valid(name: str) -> None:
    form = load_form(name)
    seen: set[str] = set()
    for index, item in enumerate(fields(form)):
        kind = item.get("type")
        assert kind in FORM_FIELD_TYPES, f"{name} item {index}: unknown type {kind!r}"
        attributes = item.get("attributes", {})
        if kind == "markdown":
            assert attributes.get("value", "").strip(), f"{name} item {index}: empty markdown"
            continue
        field_id = item.get("id")
        assert field_id and ID_PATTERN.match(field_id), f"{name} item {index}: bad or missing id"
        assert field_id not in seen, f"{name}: duplicate id {field_id}"
        seen.add(field_id)
        assert attributes.get("label", "").strip(), f"{name}: {field_id} has no label"
        if kind == "dropdown":
            options = attributes.get("options", [])
            assert options, f"{name}: {field_id} has no options"
            assert len(options) == len(set(options)), f"{name}: {field_id} repeats an option"
            assert all(isinstance(o, str) and o.strip() for o in options)
            assert "None" not in options, f"{name}: GitHub reserves the option 'None'"
        if kind == "checkboxes":
            options = attributes.get("options", [])
            assert options and all(o.get("label", "").strip() for o in options)


@pytest.mark.parametrize("name", ISSUE_FORMS)
def test_issue_form_requires_the_fields_that_make_a_report_usable(name: str) -> None:
    form = load_form(name)
    required = [
        f["id"]
        for f in fields(form)
        if f.get("type") != "markdown" and f.get("validations", {}).get("required") is True
    ]
    assert len(required) >= 3, f"{name} requires too little to be a form: {required}"
    # Every textarea or input that asks "what" must be required; optional extras are the exception.
    for expected in {
        "bug_report.yml": (
            "summary",
            "component",
            "what_happened",
            "expected_behavior",
            "steps_to_reproduce",
        ),
        "feature_request.yml": ("problem", "proposal", "component"),
        "work_item.yml": (
            "problem",
            "evidence",
            "acceptance",
            "validation",
            "priority",
            "severity",
            "workstream",
        ),
    }[name]:
        assert expected in required, f"{name}: {expected} must be required"


def test_bug_and_feature_forms_offer_the_exact_component_list() -> None:
    for name in ("bug_report.yml", "feature_request.yml"):
        options = field_by_id(load_form(name), "component")["attributes"]["options"]
        assert options == COMPONENTS, name


def test_bug_form_dropdowns() -> None:
    form = load_form("bug_report.yml")
    assert field_by_id(form, "environment_kind")["attributes"]["options"] == [
        "Azure appliance",
        "AWS appliance",
        "Local development",
        "CI",
        "Not sure",
    ]
    assert field_by_id(form, "duplicate_check")["attributes"]["options"][0]["required"] is True


def test_work_item_dropdowns_match_the_project_board_exactly() -> None:
    """The board's options are created by 390-repository-admin.yml; a form value that differs cannot be pasted in."""
    board = board_options()
    form = load_form("work_item.yml")
    for field_id, board_field in (
        ("priority", "Priority"),
        ("severity", "Severity"),
        ("workstream", "Workstream"),
        ("validation_environment", "Validation Environment"),
        ("effort", "Effort"),
    ):
        assert board_field in board, (
            f"the board field {board_field} was not found in 390-repository-admin.yml"
        )
        assert field_by_id(form, field_id)["attributes"]["options"] == board[board_field], (
            board_field
        )


def test_feature_form_boundaries_are_required_acknowledgements() -> None:
    options = field_by_id(load_form("feature_request.yml"), "boundaries")["attributes"]["options"]
    assert len(options) == 2 and all(o["required"] is True for o in options)


def test_issue_form_config_disables_blank_issues_and_routes_security_privately() -> None:
    config = yaml.safe_load((FORMS / "config.yml").read_text(encoding="utf-8"))
    assert config["blank_issues_enabled"] is False
    links = config["contact_links"]
    assert links and all({"name", "url", "about"} <= set(link) for link in links)
    assert all(link["url"].startswith("https://github.com/") for link in links)
    assert any(link["url"].endswith("/security/advisories/new") for link in links)


# --- pull request template ---


def test_pull_request_template_asks_for_the_evidence_the_repository_requires() -> None:
    text = (GITHUB / "PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")
    for heading in (
        "## Summary",
        "## Verification",
        "## Security and data",
        "## CI, containers and dependencies",
    ):
        assert heading in text, heading
    assert "Checks not run and why" in text
    assert "required checks" in text  # the reminder never to rename a 300 job
    assert "uv lock" in text
