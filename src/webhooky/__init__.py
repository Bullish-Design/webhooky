"""
WebHooky - Validation-based webhook event processing with explicit bus architecture.

Combines:
- Explicit bus + strong typing
- Validation-based pattern matching
- Enhanced observability and plugin system
"""

from __future__ import annotations

__version__ = "0.2.0"
__author__ = "Bullish Design"

# Core functionality
from .bus import EventBus
from .events import (
    WebhookEventBase,
    GenericWebhookEvent,
    on_activity,
    on_any,
    on_create,
    on_update,
    on_delete,
    on_push,
    on_pull_request,
)
from .registry import event_registry
from .plugins import plugin_manager, webhook_handler

# Configuration
from .config import (
    WebHookyConfig,
    ConfigLoader,
    ConfigValidator,
    load_config_from_env,
    create_dev_config,
    create_production_config,
    create_minimal_config,
)

# Models
from .models import (
    ProcessingResult,
    EventBusMetrics,
    PluginInfo,
    HandlerInfo,
    EventRegistryInfo,
    WebHookyStatus,
    LogLevel,
)

# Exceptions
from .exceptions import (
    WebHookyError,
    WebHookyConfigError,
    EventValidationError,
    HandlerError,
    HandlerTimeoutError,
    PluginError,
    PluginLoadError,
    PluginNotFoundError,
    EventRegistryError,
    BusError,
    AdapterError,
)

# Optional FastAPI integration
try:
    from .fastapi import (
        WebHookyFastAPI,
        create_app,
        attach_to_app,
    )

    __fastapi_available__ = True
except ImportError:
    __fastapi_available__ = False

__all__ = [
    # Core classes
    "EventBus",
    "WebhookEventBase",
    "GenericWebhookEvent",
    "event_registry",
    "plugin_manager",
    # Decorators
    "on_activity",
    "on_any",
    "on_create",
    "on_update",
    "on_delete",
    "on_push",
    "on_pull_request",
    "webhook_handler",
    # Configuration
    "WebHookyConfig",
    "ConfigLoader",
    "ConfigValidator",
    "load_config_from_env",
    "create_dev_config",
    "create_production_config",
    "create_minimal_config",
    # Models
    "ProcessingResult",
    "EventBusMetrics",
    "PluginInfo",
    "HandlerInfo",
    "EventRegistryInfo",
    "WebHookyStatus",
    "LogLevel",
    # Exceptions
    "WebHookyError",
    "WebHookyConfigError",
    "EventValidationError",
    "HandlerError",
    "HandlerTimeoutError",
    "PluginError",
    "PluginLoadError",
    "PluginNotFoundError",
    "EventRegistryError",
    "BusError",
    "AdapterError",
]

# Add FastAPI exports if available
if __fastapi_available__:
    __all__.extend(
        [
            "WebHookyFastAPI",
            "create_app",
            "attach_to_app",
        ]
    )


def get_version() -> str:
    """Get package version."""
    return __version__


def create_bus(config: WebHookyConfig = None) -> EventBus:
    """Create EventBus with configuration."""
    config = config or WebHookyConfig()
    return EventBus(
        timeout_seconds=config.timeout_seconds,
        max_concurrent_handlers=config.max_concurrent_handlers,
        swallow_exceptions=config.swallow_exceptions,
        enable_metrics=config.enable_metrics,
        activity_groups={k: set(v) for k, v in config.activity_groups.items()},
    )


def quick_setup(enable_plugins: bool = True, enable_fastapi: bool = True) -> tuple:
    """
    Quick setup for WebHooky with sensible defaults.

    Returns:
        (bus, config, app) tuple where app is None if FastAPI unavailable
    """
    config = create_dev_config(enable_plugins=enable_plugins)
    bus = create_bus(config)

    # Load plugins if enabled
    if enable_plugins:
        discovered = plugin_manager.discover_plugins()
        for plugin_name in discovered:
            plugin_manager.load_plugin(plugin_name)
        plugin_manager.register_with_bus(bus)

    # Create FastAPI app if requested and available
    app = None
    if enable_fastapi and __fastapi_available__:
        from .fastapi import create_app

        app = create_app(bus, config)

    return bus, config, app


def check_dependencies() -> dict[str, bool]:
    """Check optional dependencies availability."""
    dependencies = {}

    # FastAPI
    try:
        import fastapi

        dependencies["fastapi"] = True
    except ImportError:
        dependencies["fastapi"] = False

    # Rich (for pretty output)
    try:
        import rich

        dependencies["rich"] = True
    except ImportError:
        dependencies["rich"] = False

    return dependencies


# Example usage for documentation
def _example_usage():
    """Example usage patterns (for documentation)."""

    # Basic usage with pattern matching
    from pydantic import BaseModel, field_validator

    class GitHubPushPayload(BaseModel):
        ref: str
        repository: dict

        @field_validator("ref")
        @classmethod
        def must_be_push(cls, v):
            if not v.startswith("refs/"):
                raise ValueError("Invalid ref format")
            return v

    class GitHubPushEvent(WebhookEventBase[GitHubPushPayload]):
        @on_push()
        async def handle_push(self):
            print(f"Push to {self.payload.ref}")

    # Bus setup and handler registration
    bus = EventBus()

    @bus.on_pattern(GitHubPushEvent)
    async def process_github_push(event: GitHubPushEvent):
        print(f"Processing push: {event.payload.repository}")

    # FastAPI integration
    if __fastapi_available__:
        from .fastapi import create_app

        app = create_app(bus)
        # Now serve with: uvicorn app:app

