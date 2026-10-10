"""Unit tests for document version manager (DD-012)."""

from cna.core.version_manager import bump_version


def test_patch_bump():
    assert bump_version("1.0.0", "patch") == "1.0.1"


def test_minor_bump():
    assert bump_version("1.0.0", "minor") == "1.1.0"


def test_major_bump():
    assert bump_version("1.0.0", "major") == "2.0.0"


def test_default_is_patch():
    assert bump_version("2.3.4") == "2.3.5"
