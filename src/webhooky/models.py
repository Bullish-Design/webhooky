"""Core models and data structures for WebHooky."""

from __future__ import annotations

import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pathlib import Path

from pydantic import BaseModel, Field, ConfigDict, computed_field


class LogLevel(Enum):
    """Logging levels."""
    DEBUG = "debug"
    INFO = "info" 
    WARNING = "warning"
    ERROR = "error"


class ProcessingResult(BaseModel):
    """Result of processing a webhook event through the bus."""
    
    model_config = ConfigDict(extra="forbid")
    
    timestamp: datetime = Field(default_factory=datetime.now)
    success: bool = False
    processing_time: float = 0.0
    
    # Event data
    raw_data: Optional[Dict[str, Any]] = None
    headers: Dict[str, str] = Field(default_factory=dict)
    matched_patterns: List[str] = Field(default_factory=list)
    
    # Processing results
    handler_results: List[Dict[str, Any]] = Field(default_factory=list)
    triggered_methods: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

    @computed_field
    @property
    def handler_count(self) -> int:
        """Number of handlers that processed this event."""
        return len(self.handler_results)

    @computed_field
    @property
    def successful_handlers(self) -> int:
        """Number of handlers that succeeded."""
        return sum(1 for result in self.handler_results if result.get('success', False))

    @computed_field
    @property
    def failed_handlers(self) -> int:
        """Number of handlers that failed."""
        return self.handler_count - self.successful_handlers


class EventBusMetrics(BaseModel):
    """Metrics for EventBus performance monitoring."""
    
    model_config = ConfigDict(extra="forbid")
    
    # Event counters
    total_events: int = 0
    successful_events: int = 0
    failed_events: int = 0
    
    # Processing metrics
    total_processing_time: float = 0.0
    concurrent_handlers_peak: int = 0
    
    # Pattern matching
    pattern_matches: int = 0
    generic_fallbacks: int = 0
    
    # Handler metrics
    handler_executions: int = 0
    handler_failures: int = 0
    handler_timeouts: int = 0

    @computed_field 
    @property
    def success_rate(self) -> float:
        """Event processing success rate."""
        if self.total_events == 0:
            return 1.0
        return self.successful_events / self.total_events

    @computed_field
    @property
    def average_processing_time(self) -> float:
        """Average processing time per event."""
        if self.successful_events == 0:
            return 0.0
        return self.total_processing_time / self.successful_events

    @computed_field
    @property
    def handler_success_rate(self) -> float:
        """Handler execution success rate."""
        if self.handler_executions == 0:
            return 1.0
        return (self.handler_executions - self.handler_failures) / self.handler_executions


class PluginInfo(BaseModel):
    """Information about a WebHooky plugin."""
    
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(description="Plugin name")
    version: Optional[str] = None
    description: Optional[str] = None
    author: Optional[str] = None
    
    # Plugin capabilities
    event_classes: List[str] = Field(default_factory=list)
    handlers: List[str] = Field(default_factory=list) 
    activity_groups: Dict[str, List[str]] = Field(default_factory=dict)
    
    # Plugin state
    loaded: bool = False
    enabled: bool = True
    load_error: Optional[str] = None

    @computed_field
    @property
    def has_event_classes(self) -> bool:
        """Whether plugin provides event classes."""
        return len(self.event_classes) > 0

    @computed_field
    @property
    def has_handlers(self) -> bool:
        """Whether plugin provides handlers."""
        return len(self.handlers) > 0


class WebHookyConfig(BaseModel):
    """Configuration for WebHooky event bus and processing."""
    
    model_config = ConfigDict(extra="ignore")
    
    # Core bus settings
    timeout_seconds: float = Field(default=30.0, description="Handler timeout")
    max_concurrent_handlers: int = Field(default=50, description="Max concurrent handlers")
    swallow_exceptions: bool = Field(default=True, description="Swallow handler exceptions")
    
    # Logging and observability
    log_level: LogLevel = Field(default=LogLevel.INFO, description="Log level")
    enable_metrics: bool = Field(default=True, description="Enable metrics collection")
    metrics_log_path: Optional[Path] = Field(default=None, description="Path to log metrics")
    
    # Activity groups
    activity_groups: Dict[str, List[str]] = Field(
        default_factory=lambda: {
            "create": ["create", "created", "add", "added"],
            "update": ["update", "updated", "edit", "edited", "modify", "modified"],
            "delete": ["delete", "deleted", "remove", "removed"],
            "github": ["push", "pull_request", "issue", "release"],
        },
        description="Activity group definitions"
    )
    
    # Plugin settings
    enable_plugins: bool = Field(default=True, description="Enable plugin system")
    plugin_paths: List[Path] = Field(default_factory=list, description="Additional plugin paths")
    
    # FastAPI integration
    create_fastapi_routes: bool = Field(default=True, description="Auto-create FastAPI routes")
    api_prefix: str = Field(default="/webhooks", description="API route prefix")

    @computed_field
    @property
    def activity_groups_flat(self) -> Dict[str, str]:
        """Flat mapping of activity -> group name."""
        flat = {}
        for group_name, activities in self.activity_groups.items():
            for activity in activities:
                flat[activity] = group_name
        return flat


class HandlerInfo(BaseModel):
    """Information about a registered handler."""
    
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(description="Handler name")
    type: str = Field(description="Handler type (pattern|activity|any)")
    target: str = Field(description="Target pattern or activity")
    is_async: bool = Field(description="Whether handler is async")
    
    # Statistics
    execution_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_execution_time: float = 0.0
    last_executed: Optional[datetime] = None

    @computed_field
    @property
    def success_rate(self) -> float:
        """Handler success rate."""
        if self.execution_count == 0:
            return 1.0
        return self.success_count / self.execution_count

    @computed_field
    @property
    def average_execution_time(self) -> float:
        """Average execution time per call."""
        if self.success_count == 0:
            return 0.0
        return self.total_execution_time / self.success_count


class EventRegistryInfo(BaseModel):
    """Information about the event registry state."""
    
    model_config = ConfigDict(extra="forbid")
    
    registered_classes: List[str] = Field(default_factory=list)
    class_hierarchy: Dict[str, List[str]] = Field(default_factory=dict)
    validation_stats: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    
    @computed_field
    @property
    def total_classes(self) -> int:
        """Total number of registered event classes."""
        return len(self.registered_classes)


class WebHookyStatus(BaseModel):
    """Overall WebHooky system status."""
    
    model_config = ConfigDict(extra="forbid")
    
    # System state
    running: bool = False
    start_time: Optional[datetime] = None
    uptime_seconds: float = 0.0
    
    # Components
    bus_metrics: EventBusMetrics = Field(default_factory=EventBusMetrics)
    registry_info: EventRegistryInfo = Field(default_factory=EventRegistryInfo)
    plugin_count: int = 0
    handler_count: int = 0
    
    # Health indicators
    last_event_time: Optional[datetime] = None
    error_count_last_hour: int = 0
    
    @computed_field
    @property
    def is_healthy(self) -> bool:
        """Whether the system is healthy."""
        return (
            self.running and
            self.bus_metrics.success_rate > 0.9 and
            self.error_count_last_hour < 100
        )

    @computed_field
    @property
    def events_per_minute(self) -> float:
        """Events processed per minute."""
        if self.uptime_seconds == 0:
            return 0.0
        return (self.bus_metrics.total_events / self.uptime_seconds) * 60


# Convenience type aliases
EventPattern = str
ActivityPattern = str
HandlerFunction = Any