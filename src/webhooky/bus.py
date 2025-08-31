"""Event bus with explicit handlers and validation-based pattern matching."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict, PrivateAttr

from .events import WebhookEventBase, GenericWebhookEvent
from .models import EventBusMetrics, ProcessingResult

logger = logging.getLogger(__name__)

EventHandler = Callable[[WebhookEventBase], Any]


class EventBus(BaseModel):
    """
    Async event bus combining explicit handlers with validation-based pattern matching.
    
    Features:
    - Pattern-based event matching via validation
    - Activity-based handler routing
    - Timeout handling and error management
    - Comprehensive metrics and observability
    - Handler priority and grouping
    """
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    # Configuration
    timeout_seconds: float = 30.0
    max_concurrent_handlers: int = 50
    swallow_exceptions: bool = True
    enable_metrics: bool = True
    
    # Activity groups for logical organization
    activity_groups: Dict[str, Set[str]] = Field(default_factory=dict)
    
    # Private attributes
    _pattern_handlers: Dict[Type[WebhookEventBase], List[EventHandler]] = PrivateAttr(default_factory=dict)
    _activity_handlers: Dict[str, List[EventHandler]] = PrivateAttr(default_factory=dict)
    _any_handlers: List[EventHandler] = PrivateAttr(default_factory=list)
    _metrics: EventBusMetrics = PrivateAttr(default_factory=lambda: EventBusMetrics())
    _logger: Optional[Any] = PrivateAttr(default=None)
    _semaphore: Optional[asyncio.Semaphore] = PrivateAttr(default=None)

    def model_post_init(self, __context: Any) -> None:
        """Initialize semaphore for concurrency control."""
        self._semaphore = asyncio.Semaphore(self.max_concurrent_handlers)

    def set_logger(self, logger: Any) -> None:
        """Set custom logger instance."""
        self._logger = logger

    # Pattern-based handler registration (new validation-based matching)
    def on_pattern(self, *event_classes: Type[WebhookEventBase]):
        """Register handler for specific event patterns (classes)."""
        def decorator(handler: EventHandler):
            for event_class in event_classes:
                if event_class not in self._pattern_handlers:
                    self._pattern_handlers[event_class] = []
                self._pattern_handlers[event_class].append(handler)
                self._log('debug', f"Registered pattern handler for {event_class.__name__}")
            return handler
        return decorator

    # Activity-based handler registration (from Hooky)
    def on_activity(self, *activities: str):
        """Register handler for specific activities."""
        def decorator(handler: EventHandler):
            for activity in activities:
                if activity not in self._activity_handlers:
                    self._activity_handlers[activity] = []
                self._activity_handlers[activity].append(handler)
                self._log('debug', f"Registered activity handler for {activity}")
            return handler
        return decorator

    def on_any(self):
        """Register catch-all handler."""
        def decorator(handler: EventHandler):
            self._any_handlers.append(handler)
            self._log('debug', "Registered catch-all handler")
            return handler
        return decorator

    def on_group(self, *group_names: str):
        """Register handler for activity groups."""
        activities: Set[str] = set()
        for group in group_names:
            activities.update(self.activity_groups.get(group, set()))
        return self.on_activity(*activities) if activities else lambda x: x

    # Convenience methods
    def on_create(self): return self.on_group("create")
    def on_update(self): return self.on_group("update") 
    def on_delete(self): return self.on_group("delete")

    # Core dispatch methods
    async def dispatch_raw(
        self,
        raw_data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        source_info: Optional[Dict[str, Any]] = None
    ) -> ProcessingResult:
        """
        Dispatch raw webhook data using validation-based pattern matching.
        
        This is the main entry point for processing webhook events.
        """
        start_time = time.time()
        headers = headers or {}
        source_info = source_info or {}
        
        result = ProcessingResult(
            timestamp=datetime.now(),
            raw_data=raw_data,
            headers=headers
        )
        
        if self.enable_metrics:
            self._metrics.total_events += 1

        try:
            # Find matching event patterns
            matched_events = await self._match_patterns(raw_data, headers, source_info)
            result.matched_patterns = [event.__class__.__name__ for event in matched_events]
            
            if not matched_events:
                # Create generic event as fallback
                generic_event = GenericWebhookEvent.from_raw(raw_data, headers, source_info)
                matched_events = [generic_event]
                result.matched_patterns = ["GenericWebhookEvent"]

            # Process each matched event
            for event in matched_events:
                event_result = await self._process_event(event)
                result.handler_results.extend(event_result.handler_results)
                result.triggered_methods.extend(event_result.triggered_methods)
                result.errors.extend(event_result.errors)

            # Update metrics
            if self.enable_metrics:
                processing_time = time.time() - start_time
                self._metrics.successful_events += len(matched_events)
                self._metrics.total_processing_time += processing_time
                if result.errors:
                    self._metrics.failed_events += 1

            result.success = len(result.errors) == 0
            result.processing_time = time.time() - start_time

        except Exception as e:
            result.errors.append(f"Dispatch failed: {e}")
            result.success = False
            if self.enable_metrics:
                self._metrics.failed_events += 1
            self._log('error', f"Event dispatch failed: {e}")
            if not self.swallow_exceptions:
                raise

        return result

    async def dispatch_event(self, event: WebhookEventBase) -> ProcessingResult:
        """Dispatch a pre-created event object."""
        return await self._process_event(event)

    async def _match_patterns(
        self,
        raw_data: Dict[str, Any],
        headers: Dict[str, str],
        source_info: Dict[str, Any]
    ) -> List[WebhookEventBase]:
        """Find all event classes that match the raw data via validation."""
        matched = []
        
        # Import here to avoid circular dependency
        from .registry import event_registry
        
        for event_class in event_registry.get_event_classes():
            try:
                if event_class.matches(raw_data, headers):
                    event = event_class.from_raw(raw_data, headers, source_info)
                    matched.append(event)
                    self._log('debug', f"Pattern matched: {event_class.__name__}")
            except Exception as e:
                self._log('debug', f"Pattern match failed for {event_class.__name__}: {e}")

        return matched

    async def _process_event(self, event: WebhookEventBase) -> ProcessingResult:
        """Process a single event through handlers."""
        result = ProcessingResult(
            timestamp=datetime.now(),
            matched_patterns=[event.__class__.__name__]
        )
        
        # Collect handlers
        handlers = []
        
        # Pattern-based handlers
        event_class = event.__class__
        if event_class in self._pattern_handlers:
            handlers.extend(self._pattern_handlers[event_class])
        
        # Activity-based handlers
        activity = event.get_activity()
        if activity and activity in self._activity_handlers:
            handlers.extend(self._activity_handlers[activity])
        
        # Catch-all handlers
        handlers.extend(self._any_handlers)
        
        if not handlers:
            self._log('debug', f"No handlers for event {event.__class__.__name__}")
            return result

        # Execute handlers concurrently with timeout and semaphore
        async def run_handler(handler: EventHandler):
            async with self._semaphore:
                try:
                    start_time = time.time()
                    if asyncio.iscoroutinefunction(handler):
                        await asyncio.wait_for(handler(event), timeout=self.timeout_seconds)
                    else:
                        # Run sync handler in thread pool
                        loop = asyncio.get_event_loop()
                        await asyncio.wait_for(
                            loop.run_in_executor(None, handler, event),
                            timeout=self.timeout_seconds
                        )
                    
                    processing_time = time.time() - start_time
                    return {
                        'handler': getattr(handler, '__name__', str(handler)),
                        'success': True,
                        'processing_time': processing_time
                    }
                except Exception as e:
                    error_msg = f"Handler {getattr(handler, '__name__', handler)} failed: {e}"
                    self._log('error', error_msg)
                    if not self.swallow_exceptions:
                        raise
                    return {
                        'handler': getattr(handler, '__name__', str(handler)),
                        'success': False,
                        'error': str(e)
                    }

        # Execute all handlers
        handler_tasks = [run_handler(h) for h in handlers]
        handler_results = await asyncio.gather(*handler_tasks, return_exceptions=self.swallow_exceptions)
        
        # Process results
        for handler_result in handler_results:
            if isinstance(handler_result, dict):
                result.handler_results.append(handler_result)
                if not handler_result.get('success'):
                    result.errors.append(handler_result.get('error', 'Unknown handler error'))
            elif isinstance(handler_result, Exception):
                result.errors.append(str(handler_result))

        # Process event triggers
        try:
            triggered = await event.process_triggers()
            result.triggered_methods.extend(triggered)
        except Exception as e:
            self._log('error', f"Event trigger processing failed: {e}")
            result.errors.append(f"Trigger processing failed: {e}")

        result.success = len(result.errors) == 0
        return result

    # Registration methods
    def register_handler(self, event_class: Type[WebhookEventBase], handler: EventHandler) -> None:
        """Programmatically register a pattern handler."""
        if event_class not in self._pattern_handlers:
            self._pattern_handlers[event_class] = []
        self._pattern_handlers[event_class].append(handler)

    def register_activity_handler(self, activity: str, handler: EventHandler) -> None:
        """Programmatically register an activity handler."""
        if activity not in self._activity_handlers:
            self._activity_handlers[activity] = []
        self._activity_handlers[activity].append(handler)

    # Introspection and metrics
    def get_metrics(self) -> EventBusMetrics:
        """Get current metrics."""
        if self.enable_metrics:
            return self._metrics.model_copy()
        return EventBusMetrics()

    def get_handler_count(self) -> Dict[str, int]:
        """Get count of registered handlers by type."""
        return {
            'pattern_handlers': sum(len(handlers) for handlers in self._pattern_handlers.values()),
            'activity_handlers': sum(len(handlers) for handlers in self._activity_handlers.values()),
            'any_handlers': len(self._any_handlers)
        }

    def get_registered_patterns(self) -> List[str]:
        """Get list of registered event patterns."""
        return [cls.__name__ for cls in self._pattern_handlers.keys()]

    def get_registered_activities(self) -> List[str]:
        """Get list of registered activities."""
        return list(self._activity_handlers.keys())

    def reset_metrics(self) -> None:
        """Reset metrics counters."""
        if self.enable_metrics:
            self._metrics = EventBusMetrics()

    def _log(self, level: str, message: str) -> None:
        """Internal logging method."""
        logger_obj = self._logger or logger
        log_func = getattr(logger_obj, level, logger_obj.info)
        try:
            log_func(f"[WebHooky] {message}")
        except Exception:
            pass