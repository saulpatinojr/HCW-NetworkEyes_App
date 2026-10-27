"""Discovery coverage report.

DD-005/DD-016: Every blocked account or region is logged and included
in all final reports as a data quality caveat.
"""

from pydantic import BaseModel


class DiscoveryCoverageReport(BaseModel):
    accounts_attempted: int = 0
    accounts_succeeded: int = 0
    accounts_blocked: int = 0
    regions_attempted: list = []
    regions_succeeded: list = []
    regions_blocked: list = []
    services_unavailable: list = []
    coverage_percentage: float = 0.0
    block_reasons: list = []  # SCP, permission denied, throttle, etc.

    def calculate_coverage(self) -> None:
        if self.accounts_attempted > 0:
            self.coverage_percentage = round(
                (self.accounts_succeeded / self.accounts_attempted) * 100, 1
            )
