"""Exception classes for WebHooky."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class WebHookyError(Exception):
    """Base exception for all WebHooky errors."""
    pass


class WebHookyConfigError(WebHookyError):
    """Raised when WebHooky configuration is invalid."""
    pass


class EventValidationError(WebHookyError):
    """Raised when webhook data fails event validation."""
    
    def __init__(
        self, 
        message: str, 
        event_class: Optional[str] = None, 
        validation_errors: Optional[List[Dict[str, Any]]] = None
    ):
        super().__init__(message)
        self.event_class = event_class
        self.validation_errors = validation_errors or []


class HandlerError(WebHookyError):
    """Raised when handler execution fails."""
    
    def __init__(
        self, 
        message: str, 
        handler_name: Optional[str] = None, 
        original_error: Optional[Exception] = None
    ):
        super().__init__(message)
        self.handler_name = handler_name
        self.original_error = original_error


class HandlerTimeoutError(HandlerError):
    """Raised when handler execution times out."""
    
    def __init__(self, message: str, handler_name: Optional[str] = None, timeout_seconds: float = 0.0):
        super().__init__(message, handler_name)
        self.timeout_seconds = timeout_seconds


class PluginError(WebHookyError):
    """Base exception for plugin-related errors."""
    pass


class PluginLoadError(PluginError):
    """Raised when plugin loading fails."""
    
    def __init__(self, message: str, plugin_name: Optional[str] = None):
        super().__init__(message)
        self.plugin_name = plugin_name


class PluginNotFoundError(PluginError):
    """Raised when requested plugin is not found."""
    
    def __init__(self, message: str, plugin_name: Optional[str] = None):
        super().__init__(message)
        self.plugin_name = plugin_name


class EventRegistryError(WebHookyError):
    """Raised when event registry operations fail."""
    pass


class BusError(WebHookyError):
    """Raised when event bus operations fail."""
    pass


class AdapterError(WebHookyError):
    """Raised when adapter integration fails."""
    pass