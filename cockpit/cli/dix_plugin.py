"""Cockpit CLI — dix_plugin command.

Plugin management CLI: list, enable, disable, hot-reload plugins
from the terminal. Lazy-imports typer.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_ROOT))


def _get_app():
    try:
        import typer  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "typer is required for the dix_plugin CLI. "
            "Install with: pip install typer"
        ) from exc
    return typer


def main() -> None:
    typer = _get_app()
    app = typer.Typer(help="DIX plugin management CLI")

    @app.command("list")
    def cmd_list() -> None:
        """List all registered plugins and their states."""
        typer.echo("Plugin list:")
        try:
            from governance_engine.plugin_lifecycle.registry_loader import load_plugin_registry  # noqa: PLC0415
            plugins = load_plugin_registry()
            if not plugins:
                typer.echo("  (no plugins registered)")
                return
            for p in plugins:
                typer.echo(f"  {p.get('id', '?'):<30} {p.get('state', 'UNKNOWN')}")
        except Exception as exc:  # noqa: BLE001
            typer.echo(f"  Error loading registry: {exc}", err=True)

    @app.command("enable")
    def cmd_enable(plugin_id: str) -> None:
        """Enable a plugin by ID."""
        typer.echo(f"Enabling plugin: {plugin_id}")
        typer.echo("  (requires live runtime — run via dix_cli or cockpit UI)")

    @app.command("disable")
    def cmd_disable(plugin_id: str) -> None:
        """Disable a plugin by ID."""
        typer.echo(f"Disabling plugin: {plugin_id}")
        typer.echo("  (requires live runtime — run via dix_cli or cockpit UI)")

    @app.command("reload")
    def cmd_reload(plugin_id: str) -> None:
        """Request hot-reload of a plugin."""
        typer.echo(f"Requesting hot-reload: {plugin_id}")
        typer.echo("  (requires live runtime — run via dix_cli or cockpit UI)")

    app()


if __name__ == "__main__":
    main()
