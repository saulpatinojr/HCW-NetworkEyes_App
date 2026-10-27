import click
from rich.console import Console

from network_assessment import __version__
from network_assessment.cli.analyze import analyze
from network_assessment.cli.commands import diagram_cmd, module_cmd
from network_assessment.cli.discover import discover
from network_assessment.cli.init import init
from network_assessment.cli.publish import publish_group
from network_assessment.cli.report import report_group
from network_assessment.cli.review import review_group

console = Console()


@click.group()
@click.version_option(version=__version__)
def cli():
    """NetworkEyes — Cloud Network Assessment

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
