"""Exception classes for WebHooky."""
from __future__ import annotations

from typing import Optional


class WebHookyError(Exception):
    """Base exception for all WebHooky errors."""
    pass


class WebHookyConfigError(WebHookyError):
    """Configuration-related error."""
    pass


class EventProcessingError(WebHookyError):
    """Error during event processing."""
    
    def __init__(self, message: str, event_class: Optional[str] = None):
        super().__init__(message)
        self.event_class = event_class


class EventTimeoutError(EventProcessingError):
    """Event processing timeout."""
    
    def __init__(self, message: str, timeout_seconds: float, event_class: Optional[str] = None):
        super().__init__(message, event_class)
        self.timeout_seconds = timeout_seconds


class RegistrationError(WebHookyError):
    """Event class registration error."""
    pass
