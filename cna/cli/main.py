import click
from rich.console import Console

from cna import __version__
from cna.cli.analyze import analyze
from cna.cli.commands import diagram_cmd, module_cmd
from cna.cli.discover import discover
from cna.cli.init import init
from cna.cli.publish import publish_group
from cna.cli.report import report_group
from cna.cli.review import review_group

console = Console()


@click.group()
@click.version_option(version=__version__)
def cli():
    """CNA — Cloud Network Assessment Platform

    Multi-cloud network and security architecture discovery,
    AI-assisted analysis, diagram generation, and delivery.
    """
    pass


cli.add_command(init)
cli.add_command(discover)
cli.add_command(analyze)
cli.add_command(review_group)
cli.add_command(report_group)
cli.add_command(publish_group)
# Still stubs: the diagram and module engines have no CLI wiring yet.
cli.add_command(diagram_cmd.diagram)
cli.add_command(module_cmd.module)

if __name__ == "__main__":
    cli()
