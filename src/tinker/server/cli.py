"""tinkr-server — standalone CLI for running the Tinker server.

This is a separate binary from the `tinkr` client CLI.
Run this on any machine that has cloud credentials (EC2, Cloud Run, AKS, laptop).

  tinkr-server start                   # start with defaults
  tinkr-server start --port 9000       # custom port
  tinkr-server start --reload          # dev mode
  tinkr-server init                    # first-time setup wizard
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel

from tinker import __version__

app = typer.Typer(
    name="tinkr-server",
    help="Run and manage the Tinker observability server.",
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


@app.command("start")
def start(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes (dev only)"),
    log_level: str = typer.Option("info", "--log-level", help="Uvicorn log level"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """[bold cyan]Start the Tinker server.[/bold cyan]

    Run this on any machine that has access to your cloud observability stack.
    The server exposes a REST API that the [bold]tinkr[/bold] CLI connects to.

    Examples:

      tinkr-server start
      tinkr-server start --port 9000
      tinkr-server start --host 127.0.0.1 --reload   # dev mode
      tinkr-server start --debug                      # show backend queries
    """
    import logging
    import uvicorn

    if debug:
        log_level = "debug"
        logging.basicConfig(level=logging.DEBUG)
        for _noisy in (
            "httpcore",
            "httpx",
            "hpack",
            "h11",
            "h2",
            "botocore",
            "boto3",
            "urllib3",
            "asyncio",
            "google.auth",
            "google.api_core",
            "azure.core",
            "azure.identity",
        ):
            logging.getLogger(_noisy).setLevel(logging.WARNING)

    console.print(
        Panel.fit(
            f"[bold cyan]Tinker Server[/bold cyan]  [dim]v{__version__}[/dim]\n"
            f"Listening on [bold]http://{host}:{port}[/bold]\n"
            f"Docs: [link]http://{host}:{port}/docs[/link]"
            + ("\n[yellow]debug mode — backend queries will be logged[/yellow]" if debug else ""),
            border_style="cyan",
        )
    )

    uvicorn.run(
        "tinker.server.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
    )


@app.command("init")
def init_server() -> None:
    """[bold cyan]First-time setup wizard.[/bold cyan]

    Auto-detects cloud environment, configures Slack / notifiers, generates
    an API key, and writes [bold]~/.tinkr/config.toml[/bold] + [bold]~/.tinkr/.env[/bold].
    """
    from tinker.interfaces.init_wizard import ServerWizard

    ServerWizard().run()


def main() -> None:
    app()
