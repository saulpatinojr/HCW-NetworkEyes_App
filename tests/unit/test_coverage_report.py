"""Unit tests for discovery coverage report (DD-005/DD-016)."""

from cna.core.discovery_coverage import DiscoveryCoverageReport


def test_coverage_partial():
    r = DiscoveryCoverageReport(accounts_attempted=10, accounts_succeeded=8)
    r.calculate_coverage()
    assert r.coverage_percentage == 80.0


def test_coverage_full():
    r = DiscoveryCoverageReport(accounts_attempted=5, accounts_succeeded=5)
    r.calculate_coverage()
    assert r.coverage_percentage == 100.0


def test_coverage_zero_attempted():
    r = DiscoveryCoverageReport(accounts_attempted=0, accounts_succeeded=0)
    r.calculate_coverage()
    assert r.coverage_percentage == 0.0
