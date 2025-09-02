#!/usr/bin/env python3
"""CLI interface for WebHooky webhook processing."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import typer
    from rich.console import Console
    from rich.table import Table
    from rich.json import JSON
    from rich.panel import Panel
except ImportError as e:
    raise ImportError("CLI dependencies not installed. Install with: uv add webhooky[cli]") from e

from .bus import EventBus
from .config import (
    WebHookyConfig,
    load_config_from_env,
    create_dev_config,
    create_production_config,
    ConfigValidator,
)
from .models import LogLevel
from .registry import event_registry
from .plugins import plugin_manager
from .exceptions import WebHookyError

# CLI app setup
app = typer.Typer(
    name="webhooky",
    help="WebHooky webhook event processing CLI",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()


class OutputFormat(str, Enum):
    """Output format options."""

    json = "json"
    table = "table"
    pretty = "pretty"


def _setup_logging(verbose: int) -> None:
    """Setup logging based on verbosity level."""
    levels = [logging.WARNING, logging.INFO, logging.DEBUG]
    level = levels[min(verbose, len(levels) - 1)]
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Server host"),
    port: int = typer.Option(8000, "--port", help="Server port"),
    timeout: Optional[float] = typer.Option(None, "--timeout", help="Handler timeout seconds"),
    max_handlers: Optional[int] = typer.Option(None, "--max-handlers", help="Max concurrent handlers"),
    enable_plugins: bool = typer.Option(True, "--plugins/--no-plugins", help="Enable plugin system"),
    config_file: Optional[Path] = typer.Option(None, "--config", help="Config file path"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Increase verbosity"),
):
    """Start WebHooky FastAPI server."""
    _setup_logging(verbose)

    try:
        # Load config
        if config_file:
            # TODO: Implement config file loading
            config = create_dev_config()
        else:
            config = load_config_from_env(validate=True)
        console.print("[blue]Loaded configuration[/blue]")
        # console.print(f"{config.model_dump()}")
        # Apply CLI overrides
        if timeout is not None:
            config.timeout_seconds = timeout
        if max_handlers is not None:
            config.max_concurrent_handlers = max_handlers
        config.enable_plugins = enable_plugins

        # Create bus and app
        from .fastapi import create_app

        bus = EventBus(
            timeout_seconds=config.timeout_seconds,
            max_concurrent_handlers=config.max_concurrent_handlers,
            swallow_exceptions=config.swallow_exceptions,
            enable_metrics=config.enable_metrics,
            activity_groups={k: set(v) for k, v in config.activity_groups.items()},
        )

        app_instance = create_app(bus, config)

        console.print(f"[green]Starting WebHooky server on {host}:{port}[/green]")
        console.print(f"API endpoints: {config.api_prefix}/*")
        console.print(f"Plugins enabled: {config.enable_plugins}")

        # Start server
        import uvicorn

        uvicorn.run(app_instance, host=host, port=port, log_level="info")

    except WebHookyError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(2)


@app.command()
def test(
    payload_file: Optional[Path] = typer.Option(None, "--payload", help="JSON payload file"),
    payload_text: Optional[str] = typer.Option(None, "--json", help="JSON payload string"),
    timeout: Optional[float] = typer.Option(None, "--timeout", help="Handler timeout seconds"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Increase verbosity"),
):
    """Test webhook processing with sample data."""
    _setup_logging(verbose)

    # Load payload
    if payload_file:
        if not payload_file.exists():
            console.print(f"[red]Payload file not found: {payload_file}[/red]")
            raise typer.Exit(1)
        payload = json.loads(payload_file.read_text())
    elif payload_text:
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as e:
            console.print(f"[red]Invalid JSON: {e}[/red]")
            raise typer.Exit(1)
    else:
        # Default test payload
        payload = {"type": "test", "message": "WebHooky test event", "timestamp": "2025-01-01T00:00:00Z"}

    console.print("[blue]Testing webhook processing...[/blue]")
    console.print(Panel(JSON(json.dumps(payload, indent=2)), title="Test Payload"))

    try:
        # Create test bus
        config = create_dev_config()
        if timeout:
            config.timeout_seconds = timeout

        bus = EventBus(
            timeout_seconds=config.timeout_seconds,
            max_concurrent_handlers=config.max_concurrent_handlers,
            swallow_exceptions=False,  # Don't swallow in test mode
            enable_metrics=True,
        )

        # Load plugins
        if config.enable_plugins:
            discovered = plugin_manager.discover_plugins()
            for plugin_name in discovered:
                plugin_manager.load_plugin(plugin_name)
                console.print(f"[green]✓ Loaded plugin {plugin_name}[/green]")
            plugin_manager.register_with_bus(bus)

        # Process event
        async def run_test():
            result = await bus.dispatch_raw(payload)
            return result

        result = asyncio.run(run_test())

        # Display results
        if result.success:
            console.print("[green]✓ Processing successful[/green]")
        else:
            console.print("[red]✗ Processing failed[/red]")

        console.print(f"Matched patterns: {result.matched_patterns}")
        console.print(f"Handlers executed: {result.handler_count}")
        console.print(f"Processing time: {result.processing_time:.3f}s")

        if result.errors:
            console.print("[red]Errors:[/red]")
            for error in result.errors:
                console.print(f"  • {error}")

    except Exception as e:
        console.print(f"[red]Test failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def status(
    format: OutputFormat = typer.Option(OutputFormat.pretty, "--format", help="Output format"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Increase verbosity"),
):
    """Show WebHooky system status."""
    _setup_logging(verbose)

    try:
        # Get registry info
        registry_info = event_registry.get_registry_info()
        plugin_info = plugin_manager.get_all_plugin_info()

        data = {
            "registry": {
                "registered_classes": len(registry_info.registered_classes),
                "classes": registry_info.registered_classes,
                "validation_stats": registry_info.validation_stats,
            },
            "plugins": {
                "loaded_count": len([p for p in plugin_info.values() if p.loaded]),
                "total_count": len(plugin_info),
                "plugins": {name: info.model_dump() for name, info in plugin_info.items()},
            },
        }

        if format == OutputFormat.json:
            console.print_json(data=data)
        elif format == OutputFormat.table:
            _print_status_table(data)
        else:  # pretty
            _print_status_pretty(data)

    except Exception as e:
        console.print(f"[red]Failed to get status: {e}[/red]")
        raise typer.Exit(1)


def _print_status_table(data: Dict[str, Any]) -> None:
    """Print status in table format."""
    # Registry table
    table = Table(title="Event Registry")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    registry = data["registry"]
    table.add_row("Registered Classes", str(registry["registered_classes"]))

    for class_name in registry["classes"]:
        stats = registry["validation_stats"].get(class_name, {})
        attempts = stats.get("match_attempts", 0)
        matches = stats.get("successful_matches", 0)
        table.add_row(f"  {class_name}", f"{matches}/{attempts} matches")

    console.print(table)

    # Plugins table
    if data["plugins"]["total_count"] > 0:
        plugin_table = Table(title="Plugins")
        plugin_table.add_column("Name", style="cyan")
        plugin_table.add_column("Status", style="green")
        plugin_table.add_column("Event Classes", style="yellow")

        for name, info in data["plugins"]["plugins"].items():
            status = "✓ Loaded" if info["loaded"] else "✗ Failed"
            if not info["loaded"] and info.get("load_error"):
                status += f" ({info['load_error']})"
            event_count = len(info.get("event_classes", []))
            plugin_table.add_row(name, status, str(event_count))

        console.print(plugin_table)


def _print_status_pretty(data: Dict[str, Any]) -> None:
    """Print status in pretty format."""
    registry = data["registry"]
    plugins = data["plugins"]

    # Registry info
    console.print(
        Panel(
            f"Registered Classes: {registry['registered_classes']}\n"
            + "\n".join([f"• {cls}" for cls in registry["classes"]]),
            title="Event Registry",
            border_style="blue",
        )
    )

    # Plugin info
    if plugins["total_count"] > 0:
        plugin_text = f"Loaded: {plugins['loaded_count']}/{plugins['total_count']}\n\n"
        for name, info in plugins["plugins"].items():
            status = "✓" if info["loaded"] else "✗"
            plugin_text += f"{status} {name}"
            if not info["loaded"] and info.get("load_error"):
                plugin_text += f" - {info['load_error']}"
            plugin_text += "\n"

        console.print(Panel(plugin_text.strip(), title="Plugins", border_style="green"))


@app.command()
def validate(
    payload_file: Path = typer.Argument(..., help="JSON payload file to validate"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Increase verbosity"),
):
    """Validate payload against registered event patterns."""
    _setup_logging(verbose)

    if not payload_file.exists():
        console.print(f"[red]File not found: {payload_file}[/red]")
        raise typer.Exit(1)

    try:
        payload = json.loads(payload_file.read_text())

        console.print(f"[blue]Validating payload from {payload_file}[/blue]")

        # Load plugins first
        discovered = plugin_manager.discover_plugins()
        for plugin_name in discovered:
            plugin_manager.load_plugin(plugin_name)

        # Validate against all patterns
        validation_result = event_registry.validate_raw_data(payload)

        console.print(f"Total classes: {validation_result['total_classes']}")
        console.print(f"Matches: {len(validation_result['matches'])}")

        if validation_result["matches"]:
            console.print("[green]Matching patterns:[/green]")
            for match in validation_result["matches"]:
                console.print(f"  ✓ {match}")

        if validation_result["errors"]:
            console.print("[yellow]Validation errors:[/yellow]")
            for error in validation_result["errors"]:
                console.print(f"  ✗ {error['class']}: {error['error']}")

        if not validation_result["matches"]:
            console.print("[yellow]No patterns matched - would use GenericWebhookEvent[/yellow]")

    except json.JSONDecodeError as e:
        console.print(f"[red]Invalid JSON in {payload_file}: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Validation failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def plugins(
    action: str = typer.Argument("list", help="Action: list, load, unload"),
    plugin_name: Optional[str] = typer.Argument(None, help="Plugin name"),
    plugin_path: Optional[Path] = typer.Option(None, "--path", help="Plugin directory path"),
    format: OutputFormat = typer.Option(OutputFormat.pretty, "--format", help="Output format"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Increase verbosity"),
):
    """Manage WebHooky plugins."""
    _setup_logging(verbose)

    try:
        if action == "list":
            _list_plugins(format)
        elif action == "load" and plugin_name:
            _load_plugin(plugin_name, plugin_path)
        elif action == "unload" and plugin_name:
            _unload_plugin(plugin_name)
        elif action == "discover":
            _discover_plugins()
        else:
            console.print("[red]Invalid action or missing plugin name[/red]")
            console.print("Usage: webhooky plugins [list|load|unload|discover] [plugin-name]")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Plugin operation failed: {e}[/red]")
        raise typer.Exit(1)


def _list_plugins(format: OutputFormat) -> None:
    """List available and loaded plugins."""
    plugin_info = plugin_manager.get_all_plugin_info()

    if format == OutputFormat.json:
        console.print_json(data={name: info.model_dump() for name, info in plugin_info.items()})
        return

    if not plugin_info:
        console.print("[yellow]No plugins found[/yellow]")
        return

    if format == OutputFormat.table:
        table = Table(title="WebHooky Plugins")
        table.add_column("Name", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Version", style="yellow")
        table.add_column("Event Classes", style="blue")

        for name, info in plugin_info.items():
            status = "✓ Loaded" if info.loaded else "✗ Failed"
            if not info.loaded and info.load_error:
                status += f" ({info.load_error})"

            table.add_row(name, status, info.version or "unknown", str(len(info.event_classes)))

        console.print(table)
    else:  # pretty
        for name, info in plugin_info.items():
            status = "✓ Loaded" if info.loaded else "✗ Failed"
            panel_content = f"Status: {status}\n"
            panel_content += f"Version: {info.version or 'unknown'}\n"
            panel_content += f"Event Classes: {len(info.event_classes)}\n"
            panel_content += f"Handlers: {len(info.handlers)}"

            if not info.loaded and info.load_error:
                panel_content += f"\nError: {info.load_error}"

            console.print(Panel(panel_content, title=name, border_style="green" if info.loaded else "red"))


def _load_plugin(plugin_name: str, plugin_path: Optional[Path]) -> None:
    """Load a specific plugin."""
    if plugin_path:
        success = plugin_manager.load_directory_plugins(plugin_path)
        if plugin_name in success and success[plugin_name]:
            console.print(f"[green]✓ Loaded plugin {plugin_name} from {plugin_path}[/green]")
        else:
            console.print(f"[red]✗ Failed to load plugin {plugin_name} from {plugin_path}[/red]")
    else:
        success = plugin_manager.load_plugin(plugin_name)
        if success:
            console.print(f"[green]✓ Loaded plugin {plugin_name}[/green]")
        else:
            console.print(f"[red]✗ Failed to load plugin {plugin_name}[/red]")


def _unload_plugin(plugin_name: str) -> None:
    """Unload a specific plugin."""
    success = plugin_manager.unload_plugin(plugin_name)
    if success:
        console.print(f"[green]✓ Unloaded plugin {plugin_name}[/green]")
    else:
        console.print(f"[red]✗ Failed to unload plugin {plugin_name}[/red]")


def _discover_plugins() -> None:
    """Discover available plugins."""
    discovered = plugin_manager.discover_plugins()

    if discovered:
        console.print("[blue]Discovered plugins:[/blue]")
        for plugin_name in discovered:
            console.print(f"  • {plugin_name}")
    else:
        console.print("[yellow]No plugins discovered[/yellow]")


@app.command()
def config(
    validate: bool = typer.Option(False, "--validate", help="Validate configuration"),
    show_defaults: bool = typer.Option(False, "--defaults", help="Show default values"),
    format: OutputFormat = typer.Option(OutputFormat.pretty, "--format", help="Output format"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Increase verbosity"),
):
    """Show and validate WebHooky configuration."""
    _setup_logging(verbose)

    try:
        if show_defaults:
            config = WebHookyConfig()
        else:
            config = load_config_from_env(validate=False)

        config_dict = config.model_dump()

        if format == OutputFormat.json:
            console.print_json(data=config_dict)
        elif format == OutputFormat.table:
            table = Table(title="WebHooky Configuration")
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="green")

            for key, value in config_dict.items():
                table.add_row(key, str(value))

            console.print(table)
        else:  # pretty
            console.print(
                Panel(
                    "\n".join([f"{k}: {v}" for k, v in config_dict.items()]),
                    title="WebHooky Configuration",
                    border_style="blue",
                )
            )

        if validate:
            console.print("\n[blue]Validating configuration...[/blue]")
            try:
                ConfigValidator.validate_config(config)
                console.print("[green]✓ Configuration is valid[/green]")

                warnings = ConfigValidator.check_runtime_requirements(config)
                if warnings:
                    console.print("\n[yellow]Warnings:[/yellow]")
                    for warning in warnings:
                        console.print(f"  • {warning}")
            except Exception as e:
                console.print(f"[red]✗ Validation failed: {e}[/red]")
                raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Config operation failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def schema(
    class_name: Optional[str] = typer.Option(None, "--class", help="Specific event class"),
    format: OutputFormat = typer.Option(OutputFormat.pretty, "--format", help="Output format"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Increase verbosity"),
):
    """Show event class schemas."""
    _setup_logging(verbose)

    try:
        # Load plugins to get all schemas
        discovered = plugin_manager.discover_plugins()
        for plugin_name in discovered:
            plugin_manager.load_plugin(plugin_name)

        if class_name:
            # Show specific class info
            class_info = event_registry.get_class_info(class_name)
            if not class_info:
                console.print(f"[red]Event class not found: {class_name}[/red]")
                raise typer.Exit(1)

            if format == OutputFormat.json:
                console.print_json(data=class_info)
            else:
                console.print(
                    Panel(
                        f"Module: {class_info['module']}\n"
                        + f"Payload Type: {class_info['payload_type'] or 'Generic'}\n"
                        + f"Base Classes: {', '.join(class_info['base_classes'])}\n"
                        + f"Trigger Methods: {len(class_info['trigger_methods'])}\n"
                        + f"Validation Stats: {class_info['validation_stats']}",
                        title=f"Event Class: {class_name}",
                        border_style="blue",
                    )
                )
        else:
            # Show all schemas
            schemas = event_registry.export_schema()

            if format == OutputFormat.json:
                console.print_json(data=schemas)
            else:
                for class_name, schema in schemas.items():
                    if "error" in schema:
                        console.print(f"[red]{class_name}: {schema['error']}[/red]")
                    else:
                        properties = schema.get("properties", {})
                        console.print(
                            Panel(
                                f"Properties: {len(properties)}\n"
                                + "\n".join([f"• {prop}" for prop in properties.keys()]),
                                title=class_name,
                                border_style="green",
                            )
                        )

    except Exception as e:
        console.print(f"[red]Schema operation failed: {e}[/red]")
        raise typer.Exit(1)


def main() -> None:
    """Main CLI entry point."""
    app()


if __name__ == "__main__":
    sys.exit(main() or 0)

