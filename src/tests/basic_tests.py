"""Basic tests for WebHooky simplified library."""
from __future__ import annotations

import pytest
from typing import Dict, Any

from pydantic import field_validator

from webhooky import EventBus, WebhookEventBase, on_activity, on_push


class SampleEvent(WebhookEventBase):
    """Sample event class for testing."""
    
    @field_validator('raw_data')
    @classmethod
    def validate_test_data(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if 'test_field' not in v:
            raise ValueError("Missing test_field")
        return v
    
    @on_activity('test')
    async def handle_test(self):
        pass


class SamplePushEvent(WebhookEventBase):
    """Push event class for testing."""
    
    @classmethod
    def matches(cls, raw_data: Dict[str, Any], headers=None) -> bool:
        return raw_data.get('event_type') == 'push'
    
    @on_push()
    async def handle_push(self):
        pass


@pytest.mark.asyncio
async def test_event_registration():
    """Test event class registration."""
    bus = EventBus()
    bus.register(SampleEvent)
    
    assert 'SampleEvent' in bus.get_registered_classes()


@pytest.mark.asyncio
async def test_pattern_matching():
    """Test pattern matching with validation."""
    bus = EventBus()
    bus.register(SampleEvent)
    
    # Valid data should match
    valid_data = {'test_field': 'value', 'action': 'test'}
    result = await bus.process_webhook(valid_data)
    
    assert result.success
    assert 'SampleEvent' in result.matched_patterns
    assert len(result.triggered_methods) == 1


@pytest.mark.asyncio
async def test_custom_matching():
    """Test custom matches() method."""
    bus = EventBus()
    bus.register(SamplePushEvent)
    
    push_data = {'event_type': 'push', 'ref': 'refs/heads/main'}
    result = await bus.process_webhook(push_data)
    
    assert result.success
    assert 'SamplePushEvent' in result.matched_patterns


@pytest.mark.asyncio
async def test_trigger_methods():
    """Test trigger method execution."""
    bus = EventBus()
    bus.register(SampleEvent)
    
    data = {'test_field': 'value', 'action': 'test'}
    result = await bus.process_webhook(data)
    
    assert result.success
    assert len(result.triggered_methods) == 1
    assert 'SampleEvent.handle_test' in result.triggered_methods


@pytest.mark.asyncio
async def test_generic_fallback():
    """Test generic event fallback."""
    bus = EventBus(fallback_to_generic=True)
    
    # Data that matches no patterns
    random_data = {'random': 'data'}
    result = await bus.process_webhook(random_data)
    
    assert result.success
    assert 'GenericWebhookEvent' in result.matched_patterns


@pytest.mark.asyncio
async def test_no_fallback():
    """Test with fallback disabled."""
    bus = EventBus(fallback_to_generic=False)
    bus.register(SampleEvent)
    
    # Invalid data
    invalid_data = {'not_test_field': 'value'}
    result = await bus.process_webhook(invalid_data)
    
    assert result.success  # No errors, just no matches
    assert len(result.matched_patterns) == 0


@pytest.mark.asyncio
async def test_multiple_registrations():
    """Test registering multiple event classes."""
    bus = EventBus()
    bus.register_all(SampleEvent, SamplePushEvent)
    
    classes = bus.get_registered_classes()
    assert 'SampleEvent' in classes
    assert 'SamplePushEvent' in classes


@pytest.mark.asyncio
async def test_statistics():
    """Test bus statistics tracking."""
    bus = EventBus()
    bus.register(SampleEvent)
    
    data = {'test_field': 'value', 'action': 'test'}
    await bus.process_webhook(data)
    
    stats = bus.get_stats()
    assert stats['total_processed'] == 1
    assert stats['total_matches'] == 1
    assert stats['total_triggers'] == 1


@pytest.mark.asyncio
async def test_error_handling():
    """Test error handling in processing."""
    class ErrorEvent(WebhookEventBase):
        @on_activity('error')
        async def handle_error(self):
            raise Exception("Test error")
    
    bus = EventBus()
    bus.register(ErrorEvent)
    
    data = {'action': 'error'}
    result = await bus.process_webhook(data)
    
    assert not result.success
    assert len(result.errors) > 0
