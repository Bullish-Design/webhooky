"""Event registry for managing webhook event patterns and validation."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set, Type
from weakref import WeakSet
from datetime import datetime

from .models import EventRegistryInfo

logger = logging.getLogger(__name__)


class EventRegistry:
    """
    Registry for webhook event classes with pattern matching and validation tracking.
    
    Combines auto-registration with enhanced introspection and metrics.
    """

    def __init__(self):
        self._event_classes: Dict[str, Type] = {}
        self._class_hierarchy: Dict[str, List[str]] = {}
        self._validation_stats: Dict[str, Dict[str, int]] = {}
        self._active_instances: WeakSet = WeakSet()

    def register_event_class(self, event_class: Type) -> None:
        """Register an event class for pattern matching."""
        class_name = event_class.__name__
        
        if class_name in self._event_classes:
            logger.debug(f"Event class {class_name} already registered")
            return
            
        self._event_classes[class_name] = event_class
        
        # Track class hierarchy
        base_names = [base.__name__ for base in event_class.__bases__]
        self._class_hierarchy[class_name] = base_names
        
        # Initialize validation stats
        self._validation_stats[class_name] = {
            'match_attempts': 0,
            'successful_matches': 0,
            'validation_errors': 0,
            'creation_count': 0
        }
        
        logger.debug(f"Registered event class: {class_name}")

    def unregister_event_class(self, class_name: str) -> bool:
        """Unregister an event class."""
        if class_name in self._event_classes:
            del self._event_classes[class_name]
            self._class_hierarchy.pop(class_name, None)
            self._validation_stats.pop(class_name, None)
            logger.debug(f"Unregistered event class: {class_name}")
            return True
        return False

    def get_event_classes(self) -> List[Type]:
        """Get all registered event classes."""
        return list(self._event_classes.values())

    def get_event_class(self, class_name: str) -> Type | None:
        """Get specific event class by name."""
        return self._event_classes.get(class_name)

    def find_matching_classes(
        self, 
        raw_data: Dict[str, Any], 
        headers: Dict[str, str] = None
    ) -> List[Type]:
        """
        Find all event classes that match the given raw data.
        
        Updates validation statistics for monitoring.
        """
        headers = headers or {}
        matches = []
        
        for class_name, event_class in self._event_classes.items():
            stats = self._validation_stats[class_name]
            stats['match_attempts'] += 1
            
            try:
                if event_class.matches(raw_data, headers):
                    matches.append(event_class)
                    stats['successful_matches'] += 1
                    logger.debug(f"Pattern matched: {class_name}")
                else:
                    logger.debug(f"Pattern not matched: {class_name}")
            except Exception as e:
                stats['validation_errors'] += 1
                logger.debug(f"Validation error for {class_name}: {e}")

        return matches

    def create_events(
        self, 
        raw_data: Dict[str, Any], 
        headers: Dict[str, str] = None,
        source_info: Dict[str, Any] = None
    ) -> List[Any]:
        """Create event instances from raw data for all matching patterns."""
        headers = headers or {}
        source_info = source_info or {}
        events = []
        
        matching_classes = self.find_matching_classes(raw_data, headers)
        
        for event_class in matching_classes:
            try:
                event = event_class.from_raw(raw_data, headers, source_info)
                events.append(event)
                self._active_instances.add(event)
                
                # Update creation stats
                class_name = event_class.__name__
                self._validation_stats[class_name]['creation_count'] += 1
                
            except Exception as e:
                class_name = event_class.__name__
                self._validation_stats[class_name]['validation_errors'] += 1
                logger.error(f"Failed to create {class_name}: {e}")

        return events

    def get_registry_info(self) -> EventRegistryInfo:
        """Get current registry information and statistics."""
        return EventRegistryInfo(
            registered_classes=list(self._event_classes.keys()),
            class_hierarchy=self._class_hierarchy.copy(),
            validation_stats=self._validation_stats.copy()
        )

    def get_class_info(self, class_name: str) -> Dict[str, Any] | None:
        """Get detailed information about a specific event class."""
        if class_name not in self._event_classes:
            return None
            
        event_class = self._event_classes[class_name]
        stats = self._validation_stats[class_name]
        
        # Extract trigger methods
        trigger_methods = []
        for attr_name in dir(event_class):
            if attr_name.startswith('_'):
                continue
            attr = getattr(event_class, attr_name)
            if hasattr(attr, '_webhook_triggers'):
                trigger_methods.append({
                    'method': attr_name,
                    'triggers': list(attr._webhook_triggers)
                })
        
        # Get payload type info
        payload_type = None
        try:
            payload_type = event_class._get_payload_type()
        except Exception:
            pass
            
        return {
            'name': class_name,
            'module': event_class.__module__,
            'docstring': event_class.__doc__,
            'payload_type': payload_type.__name__ if payload_type else None,
            'base_classes': self._class_hierarchy.get(class_name, []),
            'trigger_methods': trigger_methods,
            'validation_stats': stats,
            'active_instances': len([inst for inst in self._active_instances 
                                   if isinstance(inst, event_class)])
        }

    def get_validation_stats(self) -> Dict[str, Dict[str, int]]:
        """Get validation statistics for all event classes."""
        return self._validation_stats.copy()

    def reset_stats(self) -> None:
        """Reset validation statistics."""
        for class_name in self._validation_stats:
            self._validation_stats[class_name] = {
                'match_attempts': 0,
                'successful_matches': 0,
                'validation_errors': 0,
                'creation_count': 0
            }
        logger.info("Registry statistics reset")

    def get_active_instances(self) -> List[Any]:
        """Get list of active event instances (via weak references)."""
        return list(self._active_instances)

    def cleanup_instances(self) -> int:
        """Clean up dead weak references and return count removed."""
        initial_count = len(self._active_instances)
        # WeakSet automatically removes dead references
        return initial_count - len(self._active_instances)

    def export_schema(self) -> Dict[str, Any]:
        """Export schema information for all registered event classes."""
        schema = {}
        
        for class_name, event_class in self._event_classes.items():
            try:
                # Get Pydantic model schema if available
                if hasattr(event_class, 'model_json_schema'):
                    schema[class_name] = event_class.model_json_schema()
                elif hasattr(event_class, 'schema'):
                    schema[class_name] = event_class.schema()
                else:
                    schema[class_name] = {
                        'type': 'object',
                        'properties': {},
                        'description': event_class.__doc__ or f"Schema for {class_name}"
                    }
            except Exception as e:
                logger.warning(f"Could not export schema for {class_name}: {e}")
                schema[class_name] = {
                    'error': f"Schema export failed: {e}"
                }
                
        return schema

    def validate_raw_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate raw data against all registered patterns and return results.
        
        Useful for debugging and testing pattern matching.
        """
        results = {
            'timestamp': datetime.now().isoformat(),
            'total_classes': len(self._event_classes),
            'matches': [],
            'errors': []
        }
        
        for class_name, event_class in self._event_classes.items():
            try:
                if event_class.matches(raw_data, {}):
                    results['matches'].append(class_name)
            except Exception as e:
                results['errors'].append({
                    'class': class_name,
                    'error': str(e)
                })
                
        return results


# Global singleton registry
event_registry = EventRegistry()
