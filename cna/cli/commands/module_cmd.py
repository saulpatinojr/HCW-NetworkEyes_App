import click
from rich.console import Console

console = Console()


@click.group(name="module")
def module():
    """Manage assessment modules."""
    pass


@module.command(name="list")
def list_modules():
    """List all available and installed modules (including stubs)."""
    console.print("[yellow]Phase A: TODO — module registry display[/yellow]")


@module.command(name="install")
@click.argument("module_name")
def install(module_name):
    """Install an available module."""
    console.print(f"[yellow]Phase A: TODO — install {module_name}[/yellow]")
