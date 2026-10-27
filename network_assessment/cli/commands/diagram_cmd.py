import click
from rich.console import Console

console = Console()


@click.group(name="diagram")
def diagram():
    """Generate architecture diagrams from discovered topology.

    TOP PRIORITY — Phase B.

    Types: vpc-topology, vnet-topology, account-hierarchy,
    security-overlay, traffic-flow, trust-boundaries, tgw-topology,
    lz-architecture, zerotrust-radar
    """
    pass


@diagram.command()
@click.option(
    "--type",
    "dtype",
    default="all",
    help="vpc-topology|vnet-topology|account-hierarchy|security-overlay|traffic-flow|trust-boundaries|tgw-topology|all",
)
@click.option("--platform", default="all", help="aws|azure|all")
@click.option("--region", default="all", help="us|emea|japan|all")
@click.option(
    "--format", "fmt", default="drawio,svg,png", help="Output formats: drawio,svg,png,pdf"
)
def generate(dtype, platform, region, fmt):
    """Generate diagrams from discovered topology data."""
    console.print("[bold red]Phase B: Diagram generation — TOP PRIORITY — TODO[/bold red]")


@diagram.command()
@click.argument("diagram_file")
def preview(diagram_file):
    """Preview a generated diagram."""
    console.print("[yellow]Phase B: TODO[/yellow]")
