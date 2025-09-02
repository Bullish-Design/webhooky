"""Simplified event bus with explicit registration."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Type

from .events import WebhookEventBase, GenericWebhookEvent
from .models import ProcessingResult

logger = logging.getLogger(__name__)


class EventBus:
    """
    Simplified event bus with explicit registration.
    
    Usage:
    1. Create your WebhookEventBase subclasses
    2. Register them: bus.register(MyEventClass)
    3. Process webhooks: await bus.process_webhook(raw_data, headers)
    """
    
    def __init__(self, timeout_seconds: float = 30.0, fallback_to_generic: bool = True):
        self.timeout_seconds = timeout_seconds
        self.fallback_to_generic = fallback_to_generic
        self._registered_classes: List[Type[WebhookEventBase]] = []
        self._stats = {
            'total_processed': 0,
            'total_matches': 0,
            'total_triggers': 0,
            'total_errors': 0,
        }
    
    def register(self, event_class: Type[WebhookEventBase]) -> None:
        """Register an event class for pattern matching."""
        if event_class not in self._registered_classes:
            self._registered_classes.append(event_class)
            logger.info(f"Registered event class: {event_class.__name__}")
        else:
            logger.debug(f"Event class already registered: {event_class.__name__}")
    
    def register_all(self, *event_classes: Type[WebhookEventBase]) -> None:
        """Register multiple event classes."""
        for event_class in event_classes:
            self.register(event_class)
    
    def unregister(self, event_class: Type[WebhookEventBase]) -> bool:
        """Unregister an event class."""
        if event_class in self._registered_classes:
            self._registered_classes.remove(event_class)
            logger.info(f"Unregistered event class: {event_class.__name__}")
            return True
        return False
    
    async def process_webhook(
        self,
        raw_data: Dict[str, Any],
        headers: Dict[str, str] = None,
        source_info: Dict[str, Any] = None,
    ) -> ProcessingResult:
        """
        Process incoming webhook data.
        
        1. Find all matching event classes
        2. Create instances for matches
        3. Process triggers on each instance
        """
        start_time = time.time()
        headers = headers or {}
        source_info = source_info or {}
        
        result = ProcessingResult(
            timestamp=datetime.now(),
            raw_data=raw_data,
            headers=headers,
        )
        
        self._stats['total_processed'] += 1
        
        try:
            # Find matching event classes
            matched_events = await self._find_matches(raw_data, headers, source_info)
            
            if not matched_events and self.fallback_to_generic:
                # Create generic event as fallback
                generic_event = GenericWebhookEvent.from_raw(raw_data, headers, source_info)
                matched_events = [generic_event]
                logger.debug("Using GenericWebhookEvent fallback")
            
            result.matched_patterns = [event.__class__.__name__ for event in matched_events]
            self._stats['total_matches'] += len(matched_events)
            
            # Process triggers for each matched event
            for event in matched_events:
                try:
                    triggered, trigger_errors = await asyncio.wait_for(
                        event.process_triggers(),
                        timeout=self.timeout_seconds
                    )
                    result.triggered_methods.extend(triggered)
                    result.errors.extend(trigger_errors)
                    self._stats['total_triggers'] += len(triggered)
                    self._stats['total_errors'] += len(trigger_errors)
                except asyncio.TimeoutError:
                    error = f"Timeout processing {event.__class__.__name__} after {self.timeout_seconds}s"
                    result.errors.append(error)
                    logger.error(error)
                    self._stats['total_errors'] += 1
                except Exception as e:
                    error = f"Error processing {event.__class__.__name__}: {e}"
                    result.errors.append(error)
                    logger.error(error)
                    self._stats['total_errors'] += 1
            
            result.success = len(result.errors) == 0
            
            result.processing_time = time.time() - start_time

            if matched_events:
                logger.info(
                    f"Processed webhook: {len(matched_events)} matches, "
                    f"{len(result.triggered_methods)} triggers, "
                    f"{result.processing_time:.3f}s"
                )
            else:
                logger.debug("No patterns matched webhook data")
                
        except Exception as e:
            error_msg = f"Processing failed: {e}"
            result.errors.append(error_msg)
            result.success = False
            self._stats['total_errors'] += 1
            logger.error(error_msg)
        
        
        return result
    
    async def _find_matches(
        self,
        raw_data: Dict[str, Any],
        headers: Dict[str, str],
        source_info: Dict[str, Any],
    ) -> List[WebhookEventBase]:
        """Find all event classes that match the raw data."""
        matched_events = []
        
        for event_class in self._registered_classes:
            try:
                if event_class.matches(raw_data, headers):
                    event = event_class.from_raw(raw_data, headers, source_info)
                    matched_events.append(event)
                    logger.debug(f"Matched pattern: {event_class.__name__}")
            except Exception as e:
                logger.debug(f"Match failed for {event_class.__name__}: {e}")
        
        return matched_events
    
    def get_registered_classes(self) -> List[str]:
        """Get names of all registered event classes."""
        return [cls.__name__ for cls in self._registered_classes]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get bus processing statistics."""
        return self._stats.copy()
    
    def reset_stats(self) -> None:
        """Reset processing statistics."""
        self._stats = {
            'total_processed': 0,
            'total_matches': 0,
            'total_triggers': 0,
            'total_errors': 0,
        }
        logger.info("Bus statistics reset")
