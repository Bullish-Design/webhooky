#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "webhooky",
#   "pytest>=8",
#   "pytest-asyncio>=0.23",
# ]
# ///

"""Basic tests for WebHooky core functionality."""

from __future__ import annotations

import asyncio
import pytest
from typing import Any, Dict

from pydantic import BaseModel, field_validator, ValidationError

from webhooky import EventBus, WebhookEventBase, GenericWebhookEvent, on_create, on_activity, EventValidationError
from webhooky.registry import event_registry


# Test event classes
class TestPayload(BaseModel):
    """Test payload for validation."""

    name: str
    value: int

    @field_validator("value")
    @classmethod
    def value_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Value must be positive")
        return v


class TestEvent(WebhookEventBase[TestPayload]):
    """Test event class."""

    @on_create()
    async def test_trigger(self):
        """Test trigger method."""
        pass


class StrictTestPayload(BaseModel):
    """Strict test payload that only matches specific data."""

    event_type: str
    data: Dict[str, Any]

    @field_validator("event_type")
    @classmethod
    def must_be_test_type(cls, v: str) -> str:
        if v != "strict_test":
            raise ValueError("Must be strict_test type")
        return v


class StrictTestEvent(WebhookEventBase[StrictTestPayload]):
    """Event that only matches very specific data patterns."""

    pass


# Tests
class TestWebhookEventBase:
    """Test WebhookEventBase functionality."""

    def test_matches_valid_data(self):
        """Test pattern matching with valid data."""
        valid_data = {"name": "test", "value": 42}
        assert TestEvent.matches(valid_data)

    def test_matches_invalid_data(self):
        """Test pattern matching with invalid data."""
        invalid_data = {"name": "test", "value": -1}  # Negative value
        assert not TestEvent.matches(invalid_data)

        missing_data = {"name": "test"}  # Missing value
        assert not TestEvent.matches(missing_data)

    def test_from_raw_valid(self):
        """Test event creation from valid raw data."""
        raw_data = {"name": "test", "value": 42}
        event = TestEvent.from_raw(raw_data)

        assert event.payload.name == "test"
        assert event.payload.value == 42
        assert event.event_type == "TestEvent"

    def test_from_raw_invalid(self):
        """Test event creation from invalid raw data."""
        invalid_data = {"name": "test", "value": -1}

        with pytest.raises(EventValidationError):
            TestEvent.from_raw(invalid_data)

    def test_get_activity(self):
        """Test activity extraction."""
        # Test with activity in raw data
        data_with_action = {"name": "test", "value": 42, "action": "create"}
        event = TestEvent.from_raw(data_with_action)
        assert event.get_activity() == "create"

        # Test fallback to class name
        data_without_action = {"name": "test", "value": 42}
        event = TestEvent.from_raw(data_without_action)
        assert event.get_activity() == "testevent"

    def test_strict_pattern_matching(self):
        """Test strict validation-based pattern matching."""
        # Should match
        valid_data = {"event_type": "strict_test", "data": {"foo": "bar"}}
        assert StrictTestEvent.matches(valid_data)

        # Should not match
        invalid_data = {"event_type": "other_test", "data": {"foo": "bar"}}
        assert not StrictTestEvent.matches(invalid_data)

    async def test_process_triggers(self):
        """Test trigger method processing."""
        data = {"name": "test", "value": 42, "action": "create"}
        event = TestEvent.from_raw(data)

        triggered = await event.process_triggers()
        assert "TestEvent.test_trigger" in triggered


class TestEventBus:
    """Test EventBus functionality."""

    def test_bus_creation(self):
        """Test bus creation and configuration."""
        bus = EventBus(timeout_seconds=5.0, swallow_exceptions=False)
        assert bus.timeout_seconds == 5.0
        assert not bus.swallow_exceptions

    async def test_dispatch_raw_with_pattern_match(self):
        """Test raw data dispatch with pattern matching."""
        bus = EventBus(swallow_exceptions=False)

        handler_called = False

        @bus.on_pattern(TestEvent)
        async def test_handler(event: TestEvent):
            nonlocal handler_called
            handler_called = True
            assert event.payload.name == "test"
            assert event.payload.value == 42

        # Valid data should match and call handler
        valid_data = {"name": "test", "value": 42}
        result = await bus.dispatch_raw(valid_data)

        assert result.success
        assert "TestEvent" in result.matched_patterns
        assert handler_called

    async def test_dispatch_raw_no_pattern_match(self):
        """Test raw data dispatch with no pattern matches."""
        bus = EventBus()

        handler_called = False

        @bus.on_any()
        async def catch_all_handler(event):
            nonlocal handler_called
            handler_called = True
            # Should be GenericWebhookEvent for unmatched data
            assert isinstance(event, GenericWebhookEvent)

        # Data that doesn't match TestEvent
        unmatched_data = {"unknown": "data"}
        result = await bus.dispatch_raw(unmatched_data)

        assert result.success
        assert "GenericWebhookEvent" in result.matched_patterns
        assert handler_called

    async def test_activity_based_routing(self):
        """Test activity-based handler routing."""
        bus = EventBus(activity_groups={"test": {"create", "update"}})

        group_handler_called = False
        activity_handler_called = False

        @bus.on_group("test")
        async def group_handler(event):
            nonlocal group_handler_called
            group_handler_called = True

        @bus.on_activity("create")
        async def activity_handler(event):
            nonlocal activity_handler_called
            activity_handler_called = True

        # Event with 'create' activity should trigger both handlers
        data = {"name": "test", "value": 42, "action": "create"}
        result = await bus.dispatch_raw(data)

        assert result.success
        assert group_handler_called
        assert activity_handler_called

    async def test_handler_timeout(self):
        """Test handler timeout functionality."""
        bus = EventBus(timeout_seconds=0.1, swallow_exceptions=True)

        @bus.on_any()
        async def slow_handler(event):
            """Handler that takes too long."""
            await asyncio.sleep(1.0)  # Will timeout

        result = await bus.dispatch_raw({"test": "data"})

        # Should have errors due to timeout but still succeed overall
        assert len(result.errors) > 0
        assert "timeout" in str(result.errors[0]).lower() or "failed" in str(result.errors[0]).lower()

    async def test_concurrent_handler_execution(self):
        """Test concurrent handler execution."""
        bus = EventBus(max_concurrent_handlers=2)

        execution_order = []

        @bus.on_any()
        async def handler1(event):
            execution_order.append("handler1_start")
            await asyncio.sleep(0.1)
            execution_order.append("handler1_end")

        @bus.on_any()
        async def handler2(event):
            execution_order.append("handler2_start")
            await asyncio.sleep(0.1)
            execution_order.append("handler2_end")

        result = await bus.dispatch_raw({"test": "data"})

        assert result.success
        assert "handler1_start" in execution_order
        assert "handler2_start" in execution_order
        # Both should start before either ends (concurrent execution)
        start_count = 0
        for event in execution_order:
            if "start" in event:
                start_count += 1
            elif "end" in event and start_count < 2:
                pytest.fail("Handlers did not execute concurrently")

    def test_metrics_collection(self):
        """Test metrics collection."""
        bus = EventBus(enable_metrics=True)
        metrics = bus.get_metrics()

        assert metrics.total_events == 0
        assert metrics.successful_events == 0
        assert metrics.success_rate == 1.0

    async def test_multiple_pattern_matches(self):
        """Test when multiple patterns match the same data."""
        bus = EventBus()

        handler1_called = False
        handler2_called = False

        @bus.on_pattern(TestEvent)
        async def handler1(event: TestEvent):
            nonlocal handler1_called
            handler1_called = True

        @bus.on_pattern(GenericWebhookEvent)
        async def handler2(event: GenericWebhookEvent):
            nonlocal handler2_called
            handler2_called = True

        # Data that matches TestEvent (and GenericWebhookEvent always matches)
        data = {"name": "test", "value": 42}
        result = await bus.dispatch_raw(data)

        assert result.success
        # Should match both TestEvent and GenericWebhookEvent
        assert len(result.matched_patterns) >= 1
        assert handler1_called


class TestEventRegistry:
    """Test event registry functionality."""

    def test_auto_registration(self):
        """Test that event classes auto-register."""
        # TestEvent should be auto-registered via __init_subclass__
        registry_info = event_registry.get_registry_info()
        assert "TestEvent" in registry_info.registered_classes

    def test_pattern_validation(self):
        """Test pattern validation functionality."""
        valid_data = {"name": "test", "value": 42}
        invalid_data = {"name": "test", "value": -1}

        validation_result = event_registry.validate_raw_data(valid_data)
        assert "TestEvent" in validation_result["matches"]

        validation_result = event_registry.validate_raw_data(invalid_data)
        assert "TestEvent" not in validation_result["matches"]

    def test_class_info_extraction(self):
        """Test extraction of class information."""
        class_info = event_registry.get_class_info("TestEvent")

        assert class_info is not None
        assert class_info["name"] == "TestEvent"
        assert "payload_type" in class_info
        assert len(class_info["trigger_methods"]) > 0


# Integration tests
class TestIntegration:
    """Integration tests."""

    async def test_full_pipeline(self):
        """Test complete webhook processing pipeline."""
        bus = EventBus(swallow_exceptions=False, enable_metrics=True)

        processed_events = []

        @bus.on_pattern(TestEvent)
        async def process_test_event(event: TestEvent):
            processed_events.append(event.payload.name)

        @bus.on_activity("create")
        async def process_create_activity(event):
            processed_events.append(f"create_{event.__class__.__name__}")

        # Process valid event
        data = {"name": "integration_test", "value": 100, "action": "create"}
        result = await bus.dispatch_raw(data)

        assert result.success
        assert len(processed_events) == 2  # Both handlers should be called
        assert "integration_test" in processed_events
        assert "create_TestEvent" in processed_events

        # Check metrics
        metrics = bus.get_metrics()
        assert metrics.total_events == 1
        assert metrics.successful_events == 1
        assert metrics.success_rate == 1.0


# Fixtures and utilities
@pytest.fixture
def clean_registry():
    """Clean the event registry before each test."""
    # Reset validation stats
    event_registry.reset_stats()
    yield event_registry


@pytest.fixture
def test_bus():
    """Create a test event bus."""
    return EventBus(timeout_seconds=5.0, swallow_exceptions=False, enable_metrics=True)


# Run tests
if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])

