"""The build-only lab boundary (change set I of REFACTOR_APP.md).

Static checks on the root ``Dockerfile`` (one file, two editions, the lab target installing
the engine without ``[azure]`` and copying no ``apps/``), on the lock and the extras (the
engine's base resolution carries no cloud SDK), and on the CI image job that builds the lab
target and proves ``import azure`` fails inside it. Then the same proof in a venv built from
the engine wheel with no extra, through ``cna_azure_network_engine.edition``.

The deployable lab edition, its HTTP contract and the checks on the shipped image belong to
``HCW-NetworkEyes_AddOn``; here the lab is build-only and never pushed.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from cna_azure_network_engine import edition
from tests.packaging.test_engine_wheel import PACKAGE, REPO_ROOT, _in_venv, _python, _run, _uv

DOCKERFILE = REPO_ROOT / "Dockerfile"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def _stages(text: str) -> dict[str, str]:
    """Stage name -> stage body, from every ``FROM … AS <name>`` line."""
    parts = re.split(r"^FROM\s+\S+\s+AS\s+(\S+)\s*$", text, flags=re.MULTILINE)
    # parts = [preamble, name1, body1, name2, body2, ...]
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


@pytest.fixture(scope="module")
def clean_venv(tmp_path_factory) -> Path:
    """A fresh interpreter holding only the engine wheel (no extra), as the lab image does."""
    uv = _uv()
    if uv is None:
        pytest.skip("needs uv to build the wheel and the venv")
    out = tmp_path_factory.mktemp("dist")
    built = _run([uv, "build", "--wheel", "--out-dir", str(out), str(PACKAGE)], cwd=REPO_ROOT)
    assert built.returncode == 0, built.stderr[-2000:]
    wheel = next(out.glob("cna_azure_network_engine-*.whl"))
    venv = tmp_path_factory.mktemp("venv")
    assert _run([uv, "venv", "--python", sys.executable, str(venv)]).returncode == 0
    install = _run([uv, "pip", "install", "--python", str(_python(venv)), str(wheel)])
    assert install.returncode == 0, install.stderr[-2000:]
    return venv


@pytest.fixture(scope="module")
def dockerfile() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def stages(dockerfile: str) -> dict[str, str]:
    return _stages(dockerfile)


# ── Dockerfile ───────────────────────────────────────────────────────────────


class TestDockerfile:
    def test_edition_arg_is_declared_before_the_first_from_and_defaults_to_appliance(
        self, dockerfile: str
    ):
        first_from = dockerfile.index("\nFROM ")
        assert "ARG EDITION=appliance" in dockerfile[:first_from]

    def test_both_final_stages_exist_and_the_file_ends_with_the_selected_edition(
        self, dockerfile: str, stages: dict[str, str]
    ):
        assert {"builder-lab", "final-lab", "final-appliance"} <= set(stages)
        last_line = [ln for ln in dockerfile.splitlines() if ln.strip() and not ln.startswith("#")][
            -1
        ]
        assert last_line.strip() == "FROM final-${EDITION}"

    def test_the_lab_builder_asserts_the_edition_and_installs_the_engine_without_azure(
        self, stages: dict[str, str]
    ):
        body = stages["builder-lab"]
        assert 'test "$EDITION" = "lab"' in body
        assert "--package cna-azure-network-engine" in body
        assert "./packages/cna-azure-network-engine" in body
        assert "[azure]" not in body
        assert "--extra" not in body
        assert "cna_azure_network_engine.edition" in body  # the proof runs at build time

    def test_the_lab_final_stage_ships_no_app_no_server_and_no_pip(self, stages: dict[str, str]):
        body = stages["final-lab"]
        assert "COPY --from=builder-lab /install-lab /usr/local" in body
        assert "apps/" not in body and "COPY cna/" not in body and "COPY . ." not in body
        assert "uvicorn" not in body and "EXPOSE" not in body and "HEALTHCHECK" not in body
        assert "pip uninstall -y pip" in body
        # Numeric USER (hadolint DL3066): uid 1001 is the `cna` user created two lines earlier.
        assert "--uid 1001" in body and "USER 1001" in body and "USER cna" not in body
        assert "ENV CNA_EDITION=lab" in body
        assert 'CMD ["python", "-m", "cna_azure_network_engine.edition"]' in body

    def test_the_appliance_stage_is_the_image_as_before(self, stages: dict[str, str]):
        body = stages["final-appliance"]
        assert 'ENTRYPOINT ["cna"]' in body
        assert "ENV CNA_EDITION=appliance" in body
        assert "COPY --from=builder --chown=cna:cna /install /usr/local" in body

    def test_every_base_image_is_digest_pinned(self, dockerfile: str):
        froms = re.findall(r"^FROM\s+(\S+)", dockerfile, flags=re.MULTILINE)
        for ref in froms:
            if (
                ref.startswith("final-")
                or ref.startswith("builder")
                or ref in ("uv", "drawio-fetch")
            ):
                continue
            assert "@sha256:" in ref, ref


# ── lock and extras ──────────────────────────────────────────────────────────


class TestLockAndExtras:
    def test_the_engine_declares_no_cloud_sdk_outside_the_azure_extra(self):
        import tomllib

        data = tomllib.loads(
            (REPO_ROOT / "packages" / "cna-azure-network-engine" / "pyproject.toml").read_text(
                encoding="utf-8"
            )
        )
        base = data["project"]["dependencies"]
        assert all(not dep.startswith(("azure", "msal", "boto3")) for dep in base), base
        extras = data["project"]["optional-dependencies"]
        assert "azure" in extras and any(d.startswith("azure-identity") for d in extras["azure"])

    @pytest.mark.skipif(_uv() is None, reason="needs uv to read the lock")
    def test_the_engine_only_export_from_the_lock_carries_no_cloud_sdk(self):
        result = _run(
            [
                _uv(),
                "export",
                "--locked",
                "--no-default-groups",
                "--no-emit-project",
                "--no-emit-workspace",
                "--package",
                "cna-azure-network-engine",
            ],
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stderr[-2000:]
        names = [
            line.split("==", 1)[0].strip()
            for line in result.stdout.splitlines()
            if "==" in line and not line.startswith(("#", " ", "-"))
        ]
        assert names, result.stdout[:500]
        assert not [n for n in names if n.startswith(("azure", "msal", "boto3"))], names


# ── CI ───────────────────────────────────────────────────────────────────────


class TestCi:
    def test_the_test_workflow_builds_the_lab_target_and_proves_the_boundary(self):
        text = (WORKFLOWS / "300-test-codebase.yml").read_text(encoding="utf-8")
        job = text[text.index("  lab-image:") :]
        job = job[: job.index("\n  lockfile:")]
        assert "docker build --build-arg EDITION=lab -t cna:lab ." in job
        assert "run: docker run --rm cna:lab" in job
        assert 'docker run --rm cna:lab python -c "import azure"' in job
        assert "IDENTITY_ENDPOINT" in job
        assert "push" not in job and "login" not in job

    def test_the_image_workflow_never_builds_pushes_or_lists_the_lab_target(self):
        text = (WORKFLOWS / "200-build-images.yml").read_text(encoding="utf-8")
        assert "EDITION=lab" not in text and "target: final-lab" not in text
        assert '"lab":' not in text


# ── the engine's guard ───────────────────────────────────────────────────────


class TestEditionGuard:
    def test_identity_variables_are_reported_by_name_never_value(self):
        env = {"IDENTITY_ENDPOINT": "http://169.254.169.254/metadata/identity", "HOME": "/x"}
        problems = edition.boundary_violations(env)
        assert any("IDENTITY_ENDPOINT" in p for p in problems)
        assert not any("169.254" in p for p in problems)
        assert edition.identity_env_present({"AZURE_CLIENT_SECRET": " "}) == []

    def test_assert_exits_one_with_the_lab_prefix_on_stderr(self, capsys, monkeypatch):
        monkeypatch.setattr(edition, "importable_cloud_sdks", lambda: ["azure"])
        with pytest.raises(SystemExit) as exc_info:
            edition.assert_lab_boundary({"MSI_ENDPOINT": "http://localhost"})
        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "lab edition: azure is importable" in err
        assert "lab edition: identity environment present (MSI_ENDPOINT)" in err

    def test_main_returns_zero_when_the_boundary_holds(self, monkeypatch, capsys):
        monkeypatch.setattr(edition, "importable_cloud_sdks", lambda: [])
        for name in edition.IDENTITY_ENV_VARS:
            monkeypatch.delenv(name, raising=False)
        assert edition.main() == 0
        assert "boundary holds" in capsys.readouterr().out

    def test_the_guard_imports_no_cloud_sdk_itself(self):
        source = Path(edition.__file__).read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import|from)\s+(azure|msal|boto3)\b", source, re.MULTILINE)


# ── the venv proof (the image's CMD, without Docker) ────────────────────────


class TestVenvProof:
    def test_azure_is_not_importable_and_no_cloud_distribution_is_installed(self, clean_venv: Path):
        result = _in_venv(
            clean_venv,
            "import importlib.util, importlib.metadata as m, json\n"
            "names = sorted(d.metadata['Name'].lower() for d in m.distributions())\n"
            "print(json.dumps({'azure': importlib.util.find_spec('azure') is not None, 'names': names}))",
        )
        assert result.returncode == 0, result.stderr[-2000:]
        import json

        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert payload["azure"] is False
        assert not [n for n in payload["names"] if n.startswith(("azure-", "msal", "boto3"))]

    def _edition(self, venv: Path, extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "VIRTUAL_ENV")}
        for name in edition.IDENTITY_ENV_VARS:
            env.pop(name, None)
        env.update(extra_env)
        return _run(
            [str(_python(venv)), "-I", "-m", "cna_azure_network_engine.edition"],
            cwd=str(venv),
            env=env,
        )

    def test_the_cmd_exits_zero_in_the_clean_venv(self, clean_venv: Path):
        result = self._edition(clean_venv, {})
        assert result.returncode == 0, result.stderr[-2000:]
        assert "boundary holds" in result.stdout

    @pytest.mark.parametrize("name", edition.IDENTITY_ENV_VARS)
    def test_the_cmd_exits_one_under_an_identity_variable(self, clean_venv: Path, name: str):
        result = self._edition(clean_venv, {name: "set"})
        assert result.returncode == 1
        assert f"lab edition: identity environment present ({name})" in result.stderr

    def test_the_cmd_exits_one_when_a_cloud_sdk_resolves(self, clean_venv: Path, tmp_path: Path):
        fake = tmp_path / "fake-sdk"
        (fake / "azure").mkdir(parents=True)
        (fake / "azure" / "__init__.py").write_text("", encoding="utf-8")
        site = next(p for p in clean_venv.rglob("site-packages") if p.is_dir())
        (site / "zz_fake_sdk.pth").write_text(str(fake) + "\n", encoding="utf-8")
        try:
            result = self._edition(clean_venv, {})
        finally:
            (site / "zz_fake_sdk.pth").unlink()
        assert result.returncode == 1
        assert "lab edition: azure is importable" in result.stderr
