from typing import Annotated

import typer

app = typer.Typer(invoke_without_command=True)


@app.callback()
def main(ctx: typer.Context) -> None:
    """Azure DevOps CLI-first AI pull request reviewer."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


@app.command()
def run(
    repo_root: Annotated[str, typer.Option("--repo-root")] = ".",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Run the ADO AI PR review worker."""
    typer.echo(f"repo_root={repo_root} dry_run={dry_run}")
