"""Core webhook event classes with validation-based pattern matching."""

from __future__ import annotations

import asyncio
import logging
import inspect

from typing import Any, Dict, Generic, Optional, TypeVar, get_origin, get_args
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, computed_field, ValidationError as PydanticValidationError

logger = logging.getLogger(__name__)

PayloadT = TypeVar("PayloadT", bound=BaseModel)


class AnyPayload(BaseModel):
    """Permissive payload that accepts any extra keys."""

    model_config = ConfigDict(extra="allow")


class WebhookEventBase(BaseModel, Generic[PayloadT]):
    """
    Generic webhook event with validation-based pattern matching.

    Subclass with your PayloadT to get typed events with automatic pattern matching.
    """

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=True, validate_assignment=True)

    payload: PayloadT
    headers: Dict[str, str] = {}
    source_info: Dict[str, Any] = {}
    timestamp: datetime = datetime.now()

    def __init_subclass__(cls, **kwargs):
        """Auto-register with event registry on subclass creation."""
        super().__init_subclass__(**kwargs)
        # Avoid circular import by importing here
        from .registry import event_registry

        event_registry.register_event_class(cls)
        logging.info(f"Registered event class: {cls.__name__}")

    @classmethod
    def matches(cls, raw_data: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> bool:
        """
        Check if raw webhook data matches this event pattern.

        Uses validation-based matching - if validation succeeds, pattern matches.
        """
        try:
            logging.info(f"[{cls.__name__}] Attempting to match event")
            cls.from_raw(raw_data, headers or {})
            logging.info(f"[{cls.__name__}] Event matched successfully")
            return True
        except (PydanticValidationError, ValueError, TypeError):
            logging.error(f"[{cls.__name__}] Event did not match")
            return False

    @classmethod
    def from_raw(
        cls,
        raw_data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        source_info: Optional[Dict[str, Any]] = None,
    ) -> WebhookEventBase[PayloadT]:
        """
        Create typed event from raw webhook data.

        Override _transform_raw_data to customize payload extraction.
        Raises ValidationError if data doesn't match pattern.
        """
        headers = headers or {}
        source_info = source_info or {}

        # Transform raw data to match our payload structure
        payload_data = cls._transform_raw_data(raw_data)

        # Get the PayloadT type from Generic parameters
        payload_type = cls._get_payload_type()

        # Create typed payload
        if payload_type: # and payload_type != PayloadT:
            payload = payload_type.model_validate(payload_data)
        else:
            # Fallback for base class usage
            payload = AnyPayload.model_validate(payload_data)

        return cls(payload=payload, headers=headers, source_info=source_info, timestamp=datetime.now())

    @classmethod
    def _transform_raw_data(cls, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform raw webhook data to match payload structure.

        Override this method to customize how raw data maps to your payload.
        Default: pass through unchanged.
        """
        return raw_data

    @classmethod
    def _get_payload_type(cls) -> Optional[type]:
        # 1) Prefer the field annotation (robust even if generics are erased)
        try:
            t = cls.model_fields['payload'].annotation
            # unwrap Annotated[...] if present
            if get_origin(t) is not None:
                args = [a for a in get_args(t) if isinstance(a, type)]
                if args:
                    t = args[0]
            if isinstance(t, type) and issubclass(t, BaseModel):
                return t
        except Exception as e:
            logger.error(f"Error getting payload type from model_fields: {e}")
            pass

        try:
            from typing import get_type_hints
            hint = get_type_hints(cls).get("payload")
            if inspect.isclass(hint) and issubclass(hint, BaseModel):
                return hint
        except Exception as e:
            logger.error(f"Error getting payload type from get_type_hints: {e}")
            pass

        # 2) Fallback to generics
        for base in getattr(cls, "__orig_bases__", ()):
            origin = get_origin(base)
            if origin is WebhookEventBase:
                args = get_args(base)
                if args and inspect.isclass(args[0]) and issubclass(args[0], BaseModel):
                    return args[0]
        return None

    def get_activity(self) -> Optional[str]:
        """
        Get activity string for event bus routing.

        Override to customize activity extraction logic.
        Default: look for common activity fields in payload.
        """
        payload_dict = self.payload.model_dump() if hasattr(self.payload, "model_dump") else {}

        # Common activity field names
        for field in ["action", "event", "type", "activity_type", "event_type", "activityType", "eventType"]:

            val = payload_dict.get(field)
            if isinstance(val, str) and val:
                return val
        # Use class name as fallback
        return self.__class__.__name__.lower()

    @computed_field
    @property
    def event_type(self) -> str:
        """Event type derived from class name."""
        return self.__class__.__name__

    @computed_field
    @property
    def is_valid(self) -> bool:
        """Whether this event passed validation."""
        return True  # If we got this far, validation succeeded


    async def process_triggers(self) -> list[str]:
        """
        Invoke class-method triggers (decorated with @on_activity / @on_any).
        We must inspect the *class* to see function-level attributes, then bind.
        """
        triggered: list[str] = []
        activity = self.get_activity()

        # Walk unbound callables on the class so we can see function attributes
        for name, func in inspect.getmembers(self.__class__, predicate=callable):
            if name.startswith("_"):
                continue  # skip dunders/private

            # The decorator attaches to the function object
            orig_func = getattr(func, "__func__", func)  # unbound function
            triggers = getattr(orig_func, "_webhook_triggers", None)
            if not triggers:
                continue

            if activity in triggers or "any" in triggers:
                # Re-bind to this instance and call
                bound = getattr(self, name)
                try:
                    if inspect.iscoroutinefunction(orig_func):
                        await bound()
                    else:
                        bound()
                    triggered.append(f"{self.event_type}.{name}")
                except Exception as e:
                    logger.error(f"Trigger {name} failed: {e}")

        return triggered



class GenericWebhookEvent(WebhookEventBase[AnyPayload]):
    """Generic webhook event for untyped payloads with dict-like access."""
    
    # Override the payload field to be more flexible
    payload: Dict[str, Any] = {}

    @classmethod
    def _transform_raw_data(cls, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Accept any raw data as-is for generic events."""
        return raw_data or {}

    @classmethod
    def from_raw(
        cls,
        raw_data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        source_info: Optional[Dict[str, Any]] = None,
    ) -> GenericWebhookEvent:
        """
        Create generic event from raw webhook data.
        
        Bypasses Pydantic validation for the payload to allow any data.
        """
        headers = headers or {}
        source_info = source_info or {}
        
        # Create the event with the raw data as payload
        return cls(payload=raw_data, headers=headers, source_info=source_info, timestamp=datetime.now())

    @classmethod
    def matches(cls, raw_data: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> bool:
        """Generic events match anything."""
        return True

    def get_payload_dict(self) -> Dict[str, Any]:
        """Get the payload as a dictionary."""
        return self.payload


# Trigger decorators 
def on_activity(*activities: str):
    """Decorator to mark method as webhook trigger for specific activities."""

    def decorator(func):
        if not hasattr(func, "_webhook_triggers"):
            func._webhook_triggers = set()
        func._webhook_triggers.update(activities)
        return func

    return decorator


def on_any():
    """Decorator to mark method as trigger for any activity."""
    return on_activity("any")


# Convenience trigger decorators
on_create = lambda: on_activity("create", "created")
on_update = lambda: on_activity("update", "updated", "edit", "edited")
on_delete = lambda: on_activity("delete", "deleted", "remove", "removed")
on_push = lambda: on_activity("push", "commit")
on_pull_request = lambda: on_activity("pull_request", "pr")


