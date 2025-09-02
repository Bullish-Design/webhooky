import pytest
import asyncio
import time
from unittest.mock import Mock

from webhooky.bus import EventBus
from webhooky.events import WebhookEventBase, GenericWebhookEvent
from webhooky.models import ProcessingResult

# Define a simple event for testing
class SimpleTestEvent(WebhookEventBase):
    payload: dict

    @classmethod
    def matches(cls, raw_data, headers=None):
        return "event" in raw_data and raw_data["event"] == "simple_test"

    def get_activity(self):
        return self.payload.get("action")

@pytest.mark.asyncio
async def test_bus_dispatch_raw_no_match(test_bus: EventBus):
    """Test that dispatch_raw uses GenericWebhookEvent when no pattern matches."""
    payload = {"some": "data"}
    result = await test_bus.dispatch_raw(payload)

    assert result.success is True
    assert result.matched_patterns == ["GenericWebhookEvent"]
    assert result.handler_count == 0

@pytest.mark.asyncio
async def test_bus_dispatch_pattern_match(test_bus: EventBus):
    """Test handler registration and dispatching with a specific event pattern."""
    handler_mock = Mock()

    @test_bus.on_pattern(SimpleTestEvent)
    def pattern_handler(event: SimpleTestEvent):
        handler_mock(event)

    payload = {"event": "simple_test", "id": 1}
    result = await test_bus.dispatch_raw(payload)

    assert result.success is True
    assert result.matched_patterns == ["SimpleTestEvent"]
    handler_mock.assert_called_once()
    assert isinstance(handler_mock.call_args[0][0], SimpleTestEvent)

@pytest.mark.asyncio
async def test_bus_activity_and_any_handlers(test_bus: EventBus):
    """Test that activity and catch-all handlers are triggered correctly."""
    activity_handler_mock = Mock()
    any_handler_mock = Mock()

    @test_bus.on_activity("triggered")
    def on_triggered_handler(event):
        activity_handler_mock()

    @test_bus.on_any()
    def catch_all_handler(event):
        any_handler_mock()

    payload = {"event": "simple_test", "action": "triggered"}
    await test_bus.dispatch_raw(payload)

    activity_handler_mock.assert_called_once()
    any_handler_mock.assert_called_once()

@pytest.mark.asyncio
async def test_bus_handler_timeout(test_bus: EventBus):
    """Test that a handler correctly times out."""
    test_bus.timeout_seconds = 0.1

    @test_bus.on_pattern(SimpleTestEvent)
    async def slow_handler(event):
        await asyncio.sleep(0.2)

    payload = {"event": "simple_test"}
    result = await test_bus.dispatch_raw(payload)

    assert result.success is False
    assert len(result.errors) == 1
    assert "Timeout" in result.errors[0] or "cancelled" in result.errors[0]

@pytest.mark.asyncio
async def test_bus_sync_and_async_handlers(test_bus: EventBus):
    """Ensure both sync and async handlers can run concurrently."""
    sync_called = False
    async_called = False

    @test_bus.on_pattern(SimpleTestEvent)
    def sync_handler(event):
        nonlocal sync_called
        time.sleep(0.05) # Simulate work
        sync_called = True

    @test_bus.on_pattern(SimpleTestEvent)
    async def async_handler(event):
        nonlocal async_called
        await asyncio.sleep(0.05)
        async_called = True

    payload = {"event": "simple_test"}
    result = await test_bus.dispatch_raw(payload)

    assert result.success is True
    assert sync_called is True
    assert async_called is True
