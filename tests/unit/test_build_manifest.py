"""The build manifest carries image digests (change set J of REFACTOR_APP.md).

`200-build-images.yml` writes `.deployment-catalog/latest-build.json` with `images{}` (the
tag form the appliances read today) and `digests{}` (the same keys, `name@sha256:…`, what
was scanned and signed). The committed manifest predates the digests block; when it carries
one, the keys and the digest form are checked here, and the workflow's heredoc is checked
always so the next build writes a valid one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / ".deployment-catalog" / "latest-build.json"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "200-build-images.yml"
IMAGE_KEYS = {"cli", "api", "worker", "web", "migrator"}
DIGEST_RE = re.compile(r"^docker\.io/[a-z0-9-]+/cna@sha256:[0-9a-f]{64}$")


def test_manifest_images_cover_every_published_image_and_nothing_else():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert set(data["images"]) == IMAGE_KEYS
    assert "lab" not in data.get("images", {}) and "lab" not in data.get("digests", {})


def test_manifest_digests_when_present_match_the_images_and_the_digest_form():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    digests = data.get("digests")
    if digests is None:
        return  # written by the next run of 200-build-images.yml
    assert set(digests) == set(data["images"])
    for key, value in digests.items():
        assert DIGEST_RE.match(value), (key, value)


def test_the_workflow_writes_digests_for_every_image_key_and_validates_them():
    text = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r'"digests": \{(.*?)\n\s*\}', text, re.DOTALL)
    assert match is not None
    assert set(re.findall(r'"([a-z]+)":', match.group(1))) == IMAGE_KEYS
    assert '[[ "${!v}" =~ ^sha256:[0-9a-f]{64}$ ]]' in text
    assert "secrets.DOCKERHUB_TOKEN" not in text
    assert "DOCKERHUB_OIDC_CONNECTIONID: ${{ vars.DOCKERHUB_CONNECTION }}" in text
