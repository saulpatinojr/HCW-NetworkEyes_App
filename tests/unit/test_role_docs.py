"""Least-privilege role guidance (REFACTOR_APP.md change set F).

The scan is read-only, so no document, template or UI string recommends a write role; the one
non-read need — BGP state — is a custom role whose six actions live in one JSON file. The four
places that describe roles (the help modal, the module manifest, the env template, the role
file) say the same thing, and this test keeps them from drifting apart.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE_FILE = REPO_ROOT / "docs" / "roles" / "network-assessment-bgp-reader.json"
MODULE_YAML = REPO_ROOT / "network_assessment" / "modules" / "network" / "module.yaml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
MODAL = REPO_ROOT / "apps" / "network-assessment-web" / "components" / "ui" / "sp-help-modal.tsx"

EXPECTED_ACTIONS = [
    "Microsoft.Network/virtualNetworkGateways/getBgpPeerStatus/action",
    "Microsoft.Network/virtualNetworkGateways/getLearnedRoutes/action",
    "Microsoft.Network/virtualNetworkGateways/getAdvertisedRoutes/action",
    "Microsoft.Network/virtualHubs/bgpConnections/learnedRoutes/action",
    "Microsoft.Network/virtualHubs/bgpConnections/advertisedRoutes/action",
    "Microsoft.Network/expressRouteCircuits/peerings/routeTables/read",
]
SKIP_DIRS = {"node_modules", ".next", "__pycache__", ".venv", "dist"}
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".yaml", ".yml", ".json", ".example", ".md", ".sh", ".toml"}
WRITE_ROLE = "Network Contributor"


def _project_files(*roots: Path):
    for root in roots:
        if root.is_file():
            yield root
            continue
        for path in root.rglob("*"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.is_file() and path.suffix in TEXT_SUFFIXES:
                yield path


def test_no_project_source_recommends_network_contributor():
    """The plan's acceptance grep: apps, cna, docs and .env.example mention no write role."""
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in _project_files(
            REPO_ROOT / "apps", REPO_ROOT / "network_assessment", REPO_ROOT / "docs", ENV_EXAMPLE
        )
        if WRITE_ROLE in p.read_text(encoding="utf-8", errors="replace")
    ]
    assert offenders == []


class TestCustomRoleFile:
    def test_parses_and_lists_exactly_the_six_actions(self):
        role = json.loads(ROLE_FILE.read_text(encoding="utf-8"))
        assert role["Name"] == "Network Assessment BGP Reader"
        assert role["IsCustom"] is True
        assert role["Actions"] == EXPECTED_ACTIONS
        assert role["NotActions"] == [] and role["DataActions"] == []

    def test_every_action_is_a_read_or_a_state_returning_post(self):
        role = json.loads(ROLE_FILE.read_text(encoding="utf-8"))
        for action in role["Actions"]:
            assert action.startswith("Microsoft.Network/")
            assert action.endswith(("/read", "/action"))
            assert not any(verb in action.lower() for verb in ("write", "delete"))

    def test_actions_are_dated_as_checked_and_scope_is_fictional(self):
        role = json.loads(ROLE_FILE.read_text(encoding="utf-8"))
        assert "[VERIFY" not in role["Description"]
        assert "Microsoft Learn" in role["Description"] and "2026-10-25" in role["Description"]
        assert role["AssignableScopes"] == ["/subscriptions/00000000-0000-0000-0000-000000000001"]


class TestModuleManifest:
    def test_lists_reader_permissions_and_the_custom_role_actions(self):
        manifest = yaml.safe_load(MODULE_YAML.read_text(encoding="utf-8"))
        azure = manifest["required_permissions"]["azure"]
        assert "Microsoft.Network/*/read" in azure
        assert "Microsoft.ResourceGraph/resources/read" in azure
        for action in EXPECTED_ACTIONS:
            assert action in azure
        assert not any("write" in a.lower() or "delete" in a.lower() for a in azure)

    def test_every_action_line_names_the_role_that_grants_it_and_no_verify_marker(self):
        text = MODULE_YAML.read_text(encoding="utf-8")
        azure_block = text.split("  azure:\n", 1)[1].split("\nai_recommendations_enabled", 1)[0]
        action_lines = [line for line in azure_block.splitlines() if line.strip().startswith("- ")]
        assert len(action_lines) == 8 + len(EXPECTED_ACTIONS)
        assert all("[VERIFY" not in line and "  # " in line for line in action_lines)
        assert "Checked 2026-10-25" in text


class TestGuidanceAgrees:
    def test_env_template_names_the_role_set(self):
        text = ENV_EXAMPLE.read_text(encoding="utf-8")
        for role in (
            "Reader on each assessed scope",
            "Security Reader",
            "Cost Management",
            "Log Analytics Reader",
            "Network Assessment BGP Reader",
        ):
            assert role in text
        assert "docs/roles/network-assessment-bgp-reader.json" in text

    def test_help_modal_shows_the_role_table(self):
        text = MODAL.read_text(encoding="utf-8")
        for role in (
            "Reader",
            "Security Reader",
            "Cost Management Reader",
            "Log Analytics Reader",
            "Network Assessment BGP Reader",
            "Management Group Reader",
        ):
            assert role in text
        assert "docs/roles/network-assessment-bgp-reader.json" in text
        assert "[VERIFY" not in text
