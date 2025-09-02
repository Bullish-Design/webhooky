"""Pytest configuration and fixtures for webhooky tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from typing import Dict, Any

# Add src to path so we can import webhooky
sys.path.insert(0, str(Path(__file__).parent.parent))

from webhooky import EventBus, WebhookEventBase


@pytest.fixture
def bus():
    """Create a clean EventBus for testing."""
    return EventBus(timeout_seconds=5.0, fallback_to_generic=True)


@pytest.fixture
def sample_webhook_data():
    """Basic webhook test data."""
    return {
        "action": "test",
        "event_type": "webhook_test",
        "data": {"test_field": "test_value"},
        "timestamp": "2025-01-01T00:00:00Z"
    }


@pytest.fixture
def memo_simple():
    """Simple memo data for testing."""
    return {
        'name': 'memos/test123',
        'creator': 'users/1',
        'content': '#test Simple test memo',
        'tags': ['test'],
        'create_time': {'seconds': 1756837499},
        'update_time': {'seconds': 1756837499},
        'visibility': 1,
        'property': {}
    }


@pytest.fixture
def memo_with_tasks():
    """Memo with tasks for testing."""
    return {
        'name': 'memos/task456',
        'creator': 'users/1',
        'content': '# Todo List\n- [ ] Task 1\n- [x] Task 2',
        'tags': ['todo'],
        'create_time': {'seconds': 1756837500},
        'update_time': {'seconds': 1756837500},
        'visibility': 1,
        'property': {'has_task_list': True, 'has_incomplete_tasks': True}
    }


@pytest.fixture
def webhook_headers():
    """Common webhook headers."""
    return {
        'content-type': 'application/json',
        'user-agent': 'TestWebhook/1.0',
        'x-webhook-source': 'test'
    }
