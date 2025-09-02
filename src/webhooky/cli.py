#!/usr/bin/env python3
"""Basic CLI for WebHooky."""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any

try:
    import typer
    from rich.console import Console
    from rich.json import JSON
except ImportError as e:
    raise ImportError("CLI dependencies not installed. Install with: uv add rich typer") from e

from .bus import EventBus
from .config import create_config, load_config_from_env
from .events import GenericWebhookEvent

app = typer.Typer(name="webhooky", help="WebHooky webhook processor CLI", no_args_is_help=True)
console = Console()


@app.command(no_args_is_help=True)
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Server host"),
    port: int = typer.Option(8000, "--port", help="Server port"),
    timeout: float = typer.Option(30.0, "--timeout", help="Handler timeout seconds"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Increase verbosity"),
):
    """Start WebHooky FastAPI server."""
    _setup_logging(verbose)
    
    try:
        config = create_config(
            timeout_seconds=timeout,
            host=host,
            port=port,
            enable_fastapi=True
        )
        
        from .fastapi import create_app
        
        bus = EventBus(timeout_seconds=config.timeout_seconds)
        app_instance = create_app(bus, config)
        
        console.print(f"[green]Starting WebHooky server on {host}:{port}[/green]")
        
        import uvicorn
        uvicorn.run(app_instance, host=host, port=port, log_level="info")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command(no_args_is_help=True)
def test(
    payload_file: Path = typer.Option(None, "--file", help="JSON payload file"),
    payload_json: str = typer.Option(None, "--json", help="JSON payload string"),
    timeout: float = typer.Option(30.0, "--timeout", help="Handler timeout"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Increase verbosity"),
):
    """Test webhook processing with sample data."""
    _setup_logging(verbose)
    
    # Load payload
    if payload_file:
        if not payload_file.exists():
            console.print(f"[red]File not found: {payload_file}[/red]")
            raise typer.Exit(1)
        payload = json.loads(payload_file.read_text())
    elif payload_json:
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError as e:
            console.print(f"[red]Invalid JSON: {e}[/red]")
            raise typer.Exit(1)
    else:
        # Default test payload
        payload = {
            "type": "test",
            "action": "test_webhook",
            "message": "WebHooky test event",
            "timestamp": "2025-01-01T00:00:00Z"
        }
    
    console.print("[blue]Testing webhook processing...[/blue]")
    console.print(JSON(json.dumps(payload, indent=2)))
    
    try:
        bus = EventBus(timeout_seconds=timeout, fallback_to_generic=True)
        
        async def run_test():
            result = await bus.process_webhook(payload)
            return result
        
        result = asyncio.run(run_test())
        
        if result.success:
            console.print("[green]✓ Processing successful[/green]")
        else:
            console.print("[red]✗ Processing failed[/red]")
        
        console.print(f"Matched patterns: {result.matched_patterns}")
        console.print(f"Triggered methods: {result.trigger_count}")
        console.print(f"Processing time: {result.processing_time:.3f}s")
        
        if result.errors:
            console.print("[red]Errors:[/red]")
            for error in result.errors:
                console.print(f"  • {error}")
                
    except Exception as e:
        console.print(f"[red]Test failed: {e}[/red]")
        raise typer.Exit(1)


@app.command(no_args_is_help=True)
def validate(
    payload_file: Path = typer.Argument(..., help="JSON payload file to validate"),
):
    """Validate payload structure."""
    if not payload_file.exists():
        console.print(f"[red]File not found: {payload_file}[/red]")
        raise typer.Exit(1)
    
    try:
        payload = json.loads(payload_file.read_text())
        
        # Basic validation - check if it's valid JSON
        console.print(f"[green]✓ Valid JSON with {len(payload)} fields[/green]")
        
        # Show payload structure
        console.print("Payload structure:")
        console.print(JSON(json.dumps(payload, indent=2)))
        
    except json.JSONDecodeError as e:
        console.print(f"[red]Invalid JSON: {e}[/red]")
        raise typer.Exit(1)


def _setup_logging(verbose: int) -> None:
    """Setup logging based on verbosity."""
    levels = [logging.WARNING, logging.INFO, logging.DEBUG]
    level = levels[min(verbose, len(levels) - 1)]
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> None:
    """Main CLI entry point."""
    app()


if __name__ == "__main__":
    sys.exit(main() or 0)
