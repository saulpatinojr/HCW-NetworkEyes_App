"""One Docker Hub repository, named by the owner's convention, written once per layer.

Owner decision (2026-10-25): the image this repository builds lives in its own Docker Hub
repository, ``img-<short name>-<job>-<type>`` (here ``img-ne-appliance-app``). The retired ``cna``
repository holds a different image and must never be pushed to, pruned or referenced again.

The name is defined in exactly one place per layer and read everywhere else:

* workflows: ``IMAGE_REPOSITORY`` in the workflow-level ``env`` of ``200-build-images.yml`` (the
  definition every other file is compared with), ``310-release-version.yml`` and
  ``370-registry-cleanup.yml``; every job and step reads it, none re-declares it;
* scripts: ``scripts/ci/sign_image.sh`` takes it from the ``IMAGE_REPOSITORY`` environment variable;
* contracts (``CLAUDE.md``, ``README.md``, ``REFACTOR_APP.md``, ``.env.example``, the web tier's
  image-update rules): the configured name, or a placeholder (``<repository>``).

This guard fails if the configured name leaves the convention, if the three workflows disagree, if
any workflow, script or contract names a repository other than the configured one, or if a
parallel repository variable appears. History (``CHANGELOG.md``, ``TODO.md``, ``REVIEW.md``) and the
generated ``.deployment-catalog/latest-build.json`` are not scanned: the first build after the
rename rewrites the manifest.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
BUILD_WORKFLOW = WORKFLOWS / "200-build-images.yml"
PUBLISHING_WORKFLOWS = (
    "200-build-images.yml",
    "310-release-version.yml",
    "370-registry-cleanup.yml",
)

NAME_KEY = "IMAGE_REPOSITORY"
CONVENTION = re.compile(r"^img-[a-z]{2,4}-[a-z]+-[a-z]+$")
#: Other names a second, parallel definition of the repository would likely use.
PARALLEL_KEYS = frozenset({"IMAGE_REPO", "IMAGE_NAME", "DOCKERHUB_REPO", "DOCKERHUB_REPOSITORY"})

# Image references. The namespace is written many ways across workflows (expression, shell
# variable), scripts and documents (placeholder, example), so an image reference is
# ``docker.io/<any namespace>/<repository>`` or ``<one of these namespaces>/<repository>`` (the Docker
# Hub API paths and the documents' shorthand). The repository is the segment that follows.
_NAMESPACE = (
    r"(?:<ns>|<namespace>|hybridcloudworks"
    r"|\{\{(?:env|vars)\.DOCKERHUB_NAMESPACE\}\}|\$\{?DOCKERHUB_NAMESPACE\}?|\$\{?NS\}?)"
)
_REFERENCE = re.compile(
    r"(?:docker\.io/[^/\s\"'`]+|(?<![\w.-])" + _NAMESPACE + r")/(?P<repo>[\w.${}<>-]+)"
)
#: A registry path ending in the retired name, whatever precedes it (``…/cna``, ``…/cna:tag``, ``…/cna@sha256``).
_LEGACY = re.compile(r"(?<=[\w}>-])/cna(?:[:@]|(?=[\s\"'`,;)]|$))", re.MULTILINE)
_EXPRESSION = re.compile(r"\$\{\{\s*([^}]*?)\s*\}\}")


def _normalise(text: str) -> str:
    """``${{ env.X }}`` -> ``{{env.X}}`` so an expression is one token without spaces."""
    return _EXPRESSION.sub(lambda m: "{{" + m.group(1).replace(" ", "") + "}}", text)


def _workflow(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def configured_image_repository() -> str:
    """The repository name, as ``200-build-images.yml`` defines it (the one definition)."""
    return _workflow(BUILD_WORKFLOW)["env"][NAME_KEY]


def _allowed_repository_tokens(name: str) -> set[str]:
    return {name, "${" + NAME_KEY + "}", "$" + NAME_KEY, "{{env." + NAME_KEY + "}}", "<repository>"}


def violations(text: str, name: str, *, retired_only: bool = False) -> list[str]:
    """Every image reference in ``text`` that names a repository other than ``name``.

    ``retired_only`` is for a design document that may name a sibling product's image (the AddOn's):
    it still must not name the retired repository.
    """
    text = _normalise(text)
    allowed = _allowed_repository_tokens(name)
    found = [m.group("repo").rstrip(".") for m in _REFERENCE.finditer(text)]
    problems = (
        [] if retired_only else [f"repository '{repo}'" for repo in found if repo not in allowed]
    )
    problems += [f"retired repository reference '{m.group(0)}'" for m in _LEGACY.finditer(text)]
    return problems


def _contract_files() -> list[Path]:
    """Workflows, scripts, image build files and the documents that state the image contract."""
    patterns = (
        ".github/workflows/*.yml",
        ".github/actions/**/*.yml",
        "scripts/**/*.sh",
        "Dockerfile",
        "apps/*/Dockerfile",
        "docker-compose*.yml",
        ".env.example",
        "CLAUDE.md",
        "README.md",
        "apps/cna-web/lib/image-update*.ts",
    )
    files = {
        p for pattern in patterns for p in REPO_ROOT.glob(pattern) if "node_modules" not in p.parts
    }
    return sorted(files)


#: A design document that also names a sibling product's image; checked for the retired name only.
RETIRED_ONLY_FILES = (REPO_ROOT / "REFACTOR_APP.md",)


def _find_keys(node, key: str, path: str = "") -> list[tuple[str, object]]:
    """Every ``key`` in a parsed workflow, with where it sits (``env``, ``jobs.x.env``, ``jobs.x.steps[2].env``)."""
    hits: list[tuple[str, object]] = []
    if isinstance(node, dict):
        for k, v in node.items():
            here = f"{path}.{k}" if path else str(k)
            if k == key:
                hits.append((path or "<root>", v))
            hits.extend(_find_keys(v, key, here))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            hits.extend(_find_keys(item, key, f"{path}[{i}]"))
    return hits


class TestConfiguredName:
    def test_the_name_follows_the_owner_convention(self):
        name = configured_image_repository()
        assert CONVENTION.match(name), f"'{name}' does not match {CONVENTION.pattern}"

    def test_the_retired_repository_is_not_the_configured_one(self):
        assert configured_image_repository() != "cna"


class TestDefinedOncePerWorkflow:
    @pytest.mark.parametrize("workflow", PUBLISHING_WORKFLOWS)
    def test_each_publishing_workflow_defines_it_once_at_workflow_level(self, workflow):
        hits = _find_keys(_workflow(WORKFLOWS / workflow), NAME_KEY)
        assert [where for where, _ in hits] == ["env"], (workflow, hits)

    @pytest.mark.parametrize("workflow", PUBLISHING_WORKFLOWS)
    def test_every_publishing_workflow_names_the_configured_repository(self, workflow):
        hits = _find_keys(_workflow(WORKFLOWS / workflow), NAME_KEY)
        assert [value for _, value in hits] == [configured_image_repository()], (workflow, hits)

    def test_no_other_workflow_defines_a_repository(self):
        # A new workflow that publishes or prunes images must be added to PUBLISHING_WORKFLOWS
        # (and so to the checks above), not define a name of its own.
        for path in sorted(WORKFLOWS.glob("*.yml")):
            if path.name in PUBLISHING_WORKFLOWS:
                continue
            assert not _find_keys(_workflow(path), NAME_KEY), path.name

    @pytest.mark.parametrize("path", sorted(WORKFLOWS.glob("*.yml")), ids=lambda p: p.name)
    def test_no_parallel_repository_variable(self, path):
        for key in PARALLEL_KEYS:
            assert not _find_keys(_workflow(path), key), (
                f"{path.name} defines {key}; use {NAME_KEY}"
            )


class TestNoOtherRepository:
    @pytest.mark.parametrize(
        "path", _contract_files(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix()
    )
    def test_file_names_only_the_configured_repository(self, path):
        text = path.read_text(encoding="utf-8")
        assert violations(text, configured_image_repository()) == []

    @pytest.mark.parametrize("path", RETIRED_ONLY_FILES, ids=lambda p: p.name)
    def test_the_design_document_never_names_the_retired_repository(self, path):
        text = path.read_text(encoding="utf-8")
        assert violations(text, configured_image_repository(), retired_only=True) == []
        assert configured_image_repository() in text

    def test_the_scan_sees_the_references_it_guards(self):
        # A guard whose pattern silently stopped matching would pass for the wrong reason.
        text = _normalise(BUILD_WORKFLOW.read_text(encoding="utf-8"))
        assert len(_REFERENCE.findall(text)) >= 15
        assert "{{env." + NAME_KEY + "}}" in text and "${" + NAME_KEY + "}" in text

    @pytest.mark.parametrize(
        "text",
        [
            "images: docker.io/${{ env.DOCKERHUB_NAMESPACE }}/cna",
            'IMAGE="docker.io/${DOCKERHUB_NAMESPACE}/cna"',
            "docker.io/hybridcloudworks/cna@sha256:" + "a" * 64,
            "docker.io/<ns>/cna:web-sha-<7>@sha256:<64>",
            "docker.io/hybridcloudworks/img-ca-appliance-app:latest",
            "https://hub.docker.com/v2/repositories/${DOCKERHUB_NAMESPACE}/cna/tags/",
            "docker pull ${{ env.REGISTRY }}/${{ env.DOCKERHUB_NAMESPACE }}/other-repo:latest",
            "the CLI image is `<namespace>/cna:latest`",
        ],
    )
    def test_the_scan_catches_another_repository(self, text):
        assert violations(text, "img-ne-appliance-app")

    @pytest.mark.parametrize(
        "text",
        [
            "images: docker.io/${{ env.DOCKERHUB_NAMESPACE }}/${{ env.IMAGE_REPOSITORY }}",
            'IMAGE="docker.io/${DOCKERHUB_NAMESPACE}/${IMAGE_REPOSITORY}"',
            "docker.io/hybridcloudworks/img-ne-appliance-app@sha256:" + "a" * 64,
            "scripts/ci/sign_image.sh docker.io/<namespace>/<repository>@sha256:<64>",
            "https://hub.docker.com/v2/repositories/${DOCKERHUB_NAMESPACE}/${IMAGE_REPOSITORY}/tags/",
            "docker build -t cna:local .",  # a local tag, not a Docker Hub repository
            "postgresql://cna@db.internal/cna?sslmode=disable",  # a database name
        ],
    )
    def test_the_scan_accepts_the_configured_repository_and_unrelated_names(self, text):
        assert violations(text, "img-ne-appliance-app") == []


class TestScriptsReadTheName:
    def test_sign_image_takes_the_repository_from_the_environment(self):
        text = (REPO_ROOT / "scripts" / "ci" / "sign_image.sh").read_text(encoding="utf-8")
        assert '"${IMAGE_REPOSITORY:-}"' in text
        assert "/${IMAGE_REPOSITORY}@sha256:" in text
        assert configured_image_repository() not in text

    def test_every_signing_call_passes_a_reference_built_from_the_variable(self):
        text = BUILD_WORKFLOW.read_text(encoding="utf-8")
        calls = re.findall(r"scripts/ci/sign_image\.sh \"([^\"]+)\"", text)
        assert len(calls) == 3
        for ref in calls:
            assert ref.startswith("docker.io/${DOCKERHUB_NAMESPACE}/${IMAGE_REPOSITORY}@"), ref


class TestCleanupAgreesWithTheManifest:
    """370 protects the tags the manifest of THIS repository names; 200 writes that manifest."""

    def test_the_manifest_images_are_built_from_the_variable(self):
        text = BUILD_WORKFLOW.read_text(encoding="utf-8")
        assert (
            text.count('IMAGE="docker.io/${DOCKERHUB_NAMESPACE}/${IMAGE_REPOSITORY}"') == 2
        )  # tag-images, manifest
        assert '"cli":      "${IMAGE}:${SHA_TAG}"' in text
        for role in ("api", "worker", "web", "migrator"):
            assert f'"{role}":' in text and f"${{IMAGE}}:{role}-${{SHA_TAG}}" in text
            assert f"${{IMAGE}}@${{DIGEST_{role.upper()}}}" in text

    def test_cleanup_protects_the_tags_of_the_repository_it_prunes(self):
        text = (WORKFLOWS / "370-registry-cleanup.yml").read_text(encoding="utf-8")
        assert 'MANIFEST_PREFIX="docker.io/${DOCKERHUB_NAMESPACE}/${IMAGE_REPOSITORY}:"' in text
        # The filters themselves are in the script (and run against stub manifests in
        # test_release_scripts_behaviour.py); 370 must call it with that prefix, on the committed manifest.
        assert (
            'bash scripts/ci/manifest_tags.sh protected "$MANIFEST_PREFIX" < .deployment-catalog/latest-build.json'
            in text
        )
        assert "select(startswith($prefix)) | ltrimstr($prefix)" in (
            REPO_ROOT / "scripts" / "ci" / "manifest_tags.sh"
        ).read_text(encoding="utf-8")
        # It lists and deletes tags in that same repository, never another.
        assert text.count("/${DOCKERHUB_NAMESPACE}/${IMAGE_REPOSITORY}/tags") == 2
        assert "${REPO}" not in text and 'REPO="' not in text
