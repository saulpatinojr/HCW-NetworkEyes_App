"""The engine wheel builds, installs in a clean venv with pydantic alone, and imports no cloud SDK.

Plan 7.C acceptance: ``pip install ./packages/cna-azure-network-engine`` in a clean venv installs
pydantic only; ``import cna_azure_network_engine`` leaves ``azure`` out of ``sys.modules``; no
distribution named ``azure-*``, ``msal``, ``boto3``, ``psycopg2`` or ``cna`` is present. The
build uses ``uv`` when it is on PATH (the developer and image path) and falls back to the
interpreter's ``pip`` (the CI test job).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = REPO_ROOT / "packages" / "cna-azure-network-engine"
FORBIDDEN_PREFIXES = ("azure-", "msal", "boto3", "psycopg2", "network_assessment")
_TIMEOUT = 600


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=_TIMEOUT, check=False, **kwargs
    )


def _uv() -> str | None:
    return shutil.which("uv")


def _pip_available() -> bool:
    return _run([sys.executable, "-m", "pip", "--version"]).returncode == 0


pytestmark = pytest.mark.skipif(
    _uv() is None and not _pip_available(),
    reason="needs uv or pip to build the wheel",
)


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("dist")
    if _uv():
        result = _run(
            [_uv(), "build", "--wheel", "--out-dir", str(out), str(PACKAGE)], cwd=REPO_ROOT
        )
    else:
        result = _run(
            [sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", str(out), str(PACKAGE)]
        )
    assert result.returncode == 0, result.stderr[-2000:]
    wheels = sorted(out.glob("cna_azure_network_engine-*.whl"))
    assert len(wheels) == 1, [w.name for w in out.iterdir()]
    return wheels[0]


@pytest.fixture(scope="module")
def clean_venv(tmp_path_factory, wheel: Path) -> Path:
    """A fresh interpreter with only the wheel and what it declares."""
    venv = tmp_path_factory.mktemp("venv")
    if _uv():
        assert _run([_uv(), "venv", "--python", sys.executable, str(venv)]).returncode == 0
        install = _run([_uv(), "pip", "install", "--python", str(_python(venv)), str(wheel)])
    else:
        assert _run([sys.executable, "-m", "venv", str(venv)]).returncode == 0
        install = _run([str(_python(venv)), "-m", "pip", "install", "--quiet", str(wheel)])
    assert install.returncode == 0, install.stderr[-2000:]
    return venv


def _python(venv: Path) -> Path:
    candidates = [venv / "bin" / "python", venv / "Scripts" / "python.exe"]
    return next(p for p in candidates if p.exists())


def _in_venv(venv: Path, code: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "VIRTUAL_ENV")}
    return _run([str(_python(venv)), "-I", "-c", code], cwd=str(venv), env=env)


class TestWheel:
    def test_wheel_declares_pydantic_only(self, wheel: Path):
        import zipfile

        with zipfile.ZipFile(wheel) as zf:
            metadata = next(n for n in zf.namelist() if n.endswith("METADATA"))
            text = zf.read(metadata).decode()
        requires = [
            line.split(":", 1)[1].strip()
            for line in text.splitlines()
            if line.startswith("Requires-Dist:") and "extra ==" not in line
        ]
        assert requires == ["pydantic<3,>=2.13"], requires
        assert "Requires-Python: >=3.14" in text

    def test_import_in_clean_venv_pulls_no_cloud_sdk(self, clean_venv: Path):
        result = _in_venv(
            clean_venv,
            "import sys, cna_azure_network_engine as e; "
            "print(e.RULES_VERSION, e.TOPOLOGY_MODEL_VERSION, len(e.RULES)); "
            "assert 'azure' not in sys.modules; assert 'network_assessment' not in sys.modules",
        )
        assert result.returncode == 0, result.stderr[-2000:]
        version, model, count = result.stdout.split()
        assert version == "2026.10.0" and model == "1.4.0" and int(count) == 45

    def test_clean_venv_holds_no_forbidden_distribution(self, clean_venv: Path):
        result = _in_venv(
            clean_venv,
            "import importlib.metadata as m; "
            "print('\\n'.join(sorted(d.metadata['Name'] for d in m.distributions())))",
        )
        assert result.returncode == 0, result.stderr[-2000:]
        names = [n.strip().lower() for n in result.stdout.splitlines() if n.strip()]
        assert "cna-azure-network-engine" in names
        offenders = [
            n for n in names if n.startswith(FORBIDDEN_PREFIXES) and n != "cna-azure-network-engine"
        ]
        assert offenders == [], offenders

    def test_discovery_guard_names_the_extra(self, clean_venv: Path):
        result = _in_venv(
            clean_venv,
            "from cna_azure_network_engine.discovery import require_azure_extra\n"
            "try:\n    require_azure_extra()\nexcept ImportError as exc:\n    print(exc)\nelse:\n    raise SystemExit('expected ImportError')",
        )
        assert result.returncode == 0, result.stderr[-2000:]
        assert "cna-azure-network-engine[azure]" in result.stdout

    def test_normalize_and_evaluate_run_in_the_clean_venv(self, clean_venv: Path):
        code = (
            "import cna_azure_network_engine as e\n"
            "S='00000000-0000-0000-0000-000000000001'\n"
            "rows=[{'id': f'/subscriptions/{S}/resourceGroups/hcw-sample-rg/providers/Microsoft.Network/virtualNetworks/hcw-sample-vnet',"
            " 'name': 'hcw-sample-vnet', 'type': 'microsoft.network/virtualnetworks', 'location': 'eastus',"
            " 'properties': {'addressSpace': {'addressPrefixes': ['10.0.0.0/16']}, 'enableDdosProtection': False}}]\n"
            "topo=e.normalize_resource_graph(rows)\n"
            "rep=e.evaluate(topo)\n"
            "print(topo.source, len(rep.findings), len(rep.unknowns), 'rulesVersion' in e.render_json(rep), e.render_markdown(rep).startswith('# '))"
        )
        result = _in_venv(clean_venv, code)
        assert result.returncode == 0, result.stderr[-2000:]
        source, findings, unknowns, has_version, is_md = result.stdout.split()
        assert source == "export" and int(findings) >= 1 and int(unknowns) >= 1
        assert has_version == "True" and is_md == "True"
