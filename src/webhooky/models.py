"""Core models for WebHooky."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, computed_field


class ProcessingResult(BaseModel):
    """Result of processing a webhook event through the bus."""
    
    timestamp: datetime = Field(default_factory=datetime.now)
    success: bool = False
    processing_time: float = 0.0
    
    # Event data
    raw_data: Optional[Dict[str, Any]] = None
    headers: Dict[str, str] = Field(default_factory=dict)
    matched_patterns: List[str] = Field(default_factory=list)
    
    # Processing results
    triggered_methods: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

    @computed_field
    @property
    def pattern_count(self) -> int:
        """Number of patterns that matched this webhook."""
        return len(self.matched_patterns)

    @computed_field
    @property
    def trigger_count(self) -> int:
        """Number of methods triggered by this webhook."""
        return len(self.triggered_methods)

    @computed_field
    @property
    def error_count(self) -> int:
        """Number of errors encountered during processing."""
        return len(self.errors)


class WebHookyConfig(BaseModel):
    """Configuration for WebHooky event processing."""
    
    # Core bus settings
    timeout_seconds: float = Field(default=30.0, description="Handler timeout in seconds")
    fallback_to_generic: bool = Field(default=True, description="Use generic event if no patterns match")
    
    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    
    # FastAPI integration
    enable_fastapi: bool = Field(default=True, description="Enable FastAPI integration")
    api_prefix: str = Field(default="/webhooks", description="API route prefix")
    
    # Server settings
    host: str = Field(default="127.0.0.1", description="Server host")
    port: int = Field(default=8000, description="Server port")


class WebHookyStatus(BaseModel):
    """System status information."""
    
    # System state
    running: bool = False
    start_time: Optional[datetime] = None
    uptime_seconds: float = 0.0
    
    # Registration info
    registered_classes: List[str] = Field(default_factory=list)
    class_count: int = 0
    
    # Processing stats
    total_processed: int = 0
    total_matches: int = 0
    total_triggers: int = 0
    total_errors: int = 0
    
    @computed_field
    @property
    def success_rate(self) -> float:
        """Processing success rate."""
        if self.total_processed == 0:
            return 1.0
        return (self.total_processed - self.total_errors) / self.total_processed

    @computed_field
    @property
    def average_matches_per_webhook(self) -> float:
        """Average pattern matches per webhook."""
        if self.total_processed == 0:
            return 0.0
        return self.total_matches / self.total_processed
