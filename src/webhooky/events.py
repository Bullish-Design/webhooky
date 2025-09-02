"""Core webhook event classes with simplified pattern matching."""
from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ValidationError, Field

logger = logging.getLogger(__name__)


class WebhookEventBase(BaseModel):
    """
    Base class for webhook events with structural pattern matching.
    
    Simple approach:
    1. Define validation logic in your subclass using Pydantic
    2. Override matches() for custom matching logic if needed
    3. Add @on_* decorated methods for triggers
    4. Register with EventBus: bus.register(YourEventClass)
    """
    
    raw_data: Dict[str, Any]
    headers: Dict[str, str] = Field(default_factory=dict)
    source_info: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
    
    #def __init__(self, **data):
    #    if data.get('timestamp') is None:
    #        data['timestamp'] = datetime.now()
    #    super().__init__(**data)

    @classmethod
    def matches(cls, raw_data: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> bool:
        """
        Check if raw webhook data matches this event pattern.
        
        Default: Try to validate raw_data against this model.
        Override for custom matching logic.
        """
        try:
            # Attempt to create instance - if successful, it matches
            cls(raw_data=raw_data, headers=headers or {})
            return True
        except ValidationError:
            return False
        except Exception as e:
            logger.debug(f"Match error for {cls.__name__}: {e}")
            return False

    @classmethod
    def from_raw(
        cls,
        raw_data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        source_info: Optional[Dict[str, Any]] = None,
    ) -> WebhookEventBase:
        """Create event instance from raw webhook data."""
        return cls(
            raw_data=raw_data,
            headers=headers or {},
            source_info=source_info or {},
            timestamp=datetime.now(),
        )

    def get_activity(self) -> Optional[str]:
        """
        Get activity string for routing.
        
        Override to customize activity extraction.
        Default: look for common activity fields.
        """
        for field in ['action', 'event', 'type', 'activity', 'event_type']:
            if field in self.raw_data:
                return str(self.raw_data[field])
        return self.__class__.__name__.lower()

    async def process_triggers(self) -> tuple[List[str], List[str]]:
        """
        Process all decorated trigger methods on this instance.
        
        Returns:
            (triggered_methods, errors) - Lists of successful triggers and error messages
        """
        triggered = []
        errors = []
        activity = self.get_activity()
        
        """
        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            if name.startswith('_'):
                continue

            if name in ['model_fields']:
                continue
                
            # Check for trigger decorations
            func = getattr(method, '__func__', method)
            triggers = getattr(func, '_webhook_triggers', None)
            if not triggers:
                continue
                
            # Check if this activity matches any triggers
            if 'any' in triggers or activity in triggers:
                try:
                    if inspect.iscoroutinefunction(func):
                        await method()
                    else:
                        method()
                    triggered.append(f"{self.__class__.__name__}.{name}")
                    logger.debug(f"Triggered: {self.__class__.__name__}.{name}")
                except Exception as e:
                    error_msg = f"Trigger {self.__class__.__name__}.{name} failed: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
        """
                    
        # Enumerate *class* functions to avoid getattr()-ing every instance attribute,
        # which triggers Pydantic's deprecation warnings on instance-side fields.
        for name, func in inspect.getmembers(self.__class__, predicate=inspect.isfunction):
            if name.startswith('_'):
                continue
            triggers = getattr(func, '_webhook_triggers', None)
            if not triggers:
                continue
            if 'any' in triggers or activity in triggers:
                bound = getattr(self, name)  # bind the function to this instance
                try:
                    if asyncio.iscoroutinefunction(func):
                        await bound()
                    else:
                        bound()
                    triggered.append(f"{self.__class__.__name__}.{name}")
                    logger.debug(f"Triggered: {self.__class__.__name__}.{name}")
                except Exception as e:
                    error_msg = f"Trigger {self.__class__.__name__}.{name} failed: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    
        return triggered, errors
    
    
        


class GenericWebhookEvent(WebhookEventBase):
    """Generic webhook event that matches any data."""
    
    @classmethod
    def matches(cls, raw_data: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> bool:
        """Generic events match anything."""
        return True


# Trigger decorators
def on_activity(*activities: str):
    """Mark method as webhook trigger for specific activities."""
    def decorator(func):
        if not hasattr(func, '_webhook_triggers'):
            func._webhook_triggers = set()
        func._webhook_triggers.update(activities)
        return func
    return decorator


def on_any():
    """Mark method as trigger for any activity."""
    return on_activity('any')


# Convenience decorators
def on_create():
    """Trigger on create/created activities."""
    return on_activity('create', 'created', 'add', 'added')


def on_update():
    """Trigger on update/edit activities."""  
    return on_activity('update', 'updated', 'edit', 'edited', 'modify', 'modified')


def on_delete():
    """Trigger on delete/remove activities."""
    return on_activity('delete', 'deleted', 'remove', 'removed')


def on_push():
    """Trigger on push/commit activities."""
    return on_activity('push', 'commit')


def on_pull_request():
    """Trigger on pull request activities."""
    return on_activity('pull_request', 'pr', 'merge_request', 'mr')
