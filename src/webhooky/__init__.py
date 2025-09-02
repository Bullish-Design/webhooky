"""
WebHooky - Simple Pydantic-based webhook event processing.

Simplified approach with explicit registration and pattern matching.
"""
from __future__ import annotations

__version__ = "0.3.0"
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

# Models
from .models import ProcessingResult, WebHookyConfig, WebHookyStatus

# Exceptions
from .exceptions import (
    WebHookyError,
    WebHookyConfigError,
    EventProcessingError,
    EventTimeoutError,
    RegistrationError,
)

# Configuration
from .config import create_config, load_config_from_env

# Optional FastAPI integration
try:
    from .fastapi import create_app, WebHookyFastAPI
    __fastapi_available__ = True
except ImportError:
    __fastapi_available__ = False

__all__ = [
    # Core classes
    "EventBus",
    "WebhookEventBase", 
    "GenericWebhookEvent",
    
    # Decorators
    "on_activity",
    "on_any",
    "on_create",
    "on_update",
    "on_delete",
    "on_push",
    "on_pull_request",
    
    # Models
    "ProcessingResult",
    "WebHookyConfig",
    "WebHookyStatus",
    
    # Exceptions
    "WebHookyError",
    "WebHookyConfigError",
    "EventProcessingError",
    "EventTimeoutError",
    "RegistrationError",
    
    # Configuration
    "create_config",
    "load_config_from_env",
]

# Add FastAPI exports if available
if __fastapi_available__:
    __all__.extend(["create_app", "WebHookyFastAPI"])


def get_version() -> str:
    """Get package version."""
    return __version__


def quick_start(
    event_classes: list = None, 
    timeout_seconds: float = 30.0,
    enable_fastapi: bool = True
) -> tuple:
    """
    Quick setup for WebHooky with sensible defaults.
    
    Args:
        event_classes: List of event classes to register
        timeout_seconds: Handler timeout
        enable_fastapi: Whether to create FastAPI app
    
    Returns:
        (bus, app) tuple where app is None if FastAPI unavailable
    """
    # Create bus
    bus = EventBus(timeout_seconds=timeout_seconds)
    
    # Register event classes
    if event_classes:
        bus.register_all(*event_classes)
    
    # Create FastAPI app if requested and available
    app = None
    if enable_fastapi and __fastapi_available__:
        config = WebHookyConfig(timeout_seconds=timeout_seconds)
        app = create_app(bus, config)
    
    return bus, app


def check_dependencies() -> dict[str, bool]:
    """Check optional dependencies availability."""
    dependencies = {"fastapi": __fastapi_available__}
    
    # Check other optional dependencies
    try:
        import rich
        dependencies["rich"] = True
    except ImportError:
        dependencies["rich"] = False
    
    return dependencies
