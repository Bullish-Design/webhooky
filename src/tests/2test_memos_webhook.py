# test_memos_webhook.py
import pytest
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from webhooky import (
    WebhookEventBase,
    EventBus,
    on_activity,
    on_create,
    on_update,
    on_delete,
    ProcessingResult,
    GenericWebhookEvent
)

# Define test data
MEMO_DATA_1 = {
    'name': 'memos/kMfMonuFoFWFNCGT4q7Ssm',
    'state': 1,
    'creator': 'users/1',
    'create_time': {'seconds': 1756837499},
    'update_time': {'seconds': 1756837499},
    'display_time': {'seconds': 1756837499},
    'content': '#idea testing an idea tag',
    'nodes': [{
        'type': 2,
        'Node': {
            'ParagraphNode': {
                'children': [
                    {
                        'type': 59,
                        'Node': {'TagNode': {'content': 'idea'}}
                    },
                    {
                        'type': 51,
                        'Node': {'TextNode': {'content': ' testing an idea tag'}}
                    }
                ]
            }
        }
    }],
    'visibility': 1,
    'tags': ['idea'],
    'property': {},
    'snippet': '#idea testing an idea tag\n'
}

MEMO_DATA_2 = {
    'name': 'memos/EZMx97CjKvre6h6jM7ouoC',
    'state': 1,
    'creator': 'users/1',
    'create_time': {'seconds': 1756838479},
    'update_time': {'seconds': 1756838479},
    'display_time': {'seconds': 1756838479},
    'content': "#idea #project But what if there's multiple tags?\n\n- even worse, lists?\n- [ ] heaven forbid todos...",
    'nodes': [{
        'type': 2,
        'Node': {
            'ParagraphNode': {
                'children': [
                    {
                        'type': 59,
                        'Node': {'TagNode': {'content': 'idea'}}
                    },
                    {
                        'type': 51,
                        'Node': {'TextNode': {'content': ' '}}
                    },
                    {
                        'type': 59,
                        'Node': {'TagNode': {'content': 'project'}}
                    },
                    {
                        'type': 51,
                        'Node': {'TextNode': {'content': " But what if there's multiple tags?"}}
                    }
                ]
            }
        }
    }, {
        'type': 1,
        'Node': {'LineBreakNode': None}
    }, {
        'type': 1,
        'Node': {'LineBreakNode': None}
    }, {
        'type': 7,
        'Node': {
            'ListNode': {
                'kind': 2,
                'children': [{
                    'type': 9,
                    'Node': {
                        'UnorderedListItemNode': {
                            'symbol': '-',
                            'children': [{
                                'type': 51,
                                'Node': {'TextNode': {'content': 'even worse, lists?'}}
                            }]
                        }
                    }
                }, {
                    'type': 1,
                    'Node': {'LineBreakNode': None}
                }]
            }
        }
    }, {
        'type': 7,
        'Node': {
            'ListNode': {
                'kind': 3,
                'children': [{
                    'type': 10,
                    'Node': {
                        'TaskListItemNode': {
                            'symbol': '-',
                            'children': [{
                                'type': 51,
                                'Node': {'TextNode': {'content': 'heaven forbid todos...'}}
                            }]
                        }
                    }
                }]
            }
        }
    }],
    'visibility': 1,
    'tags': ['idea', 'project'],
    'property': {'has_task_list': True, 'has_incomplete_tasks': True},
    'snippet': "#idea #project But what if there's multiple tags?\n\n-even worse, ..."
}

# Define Pydantic models for memos
class TimeInfo(BaseModel):
    seconds: int

class MemoPayload(BaseModel):
    name: str
    state: int
    creator: str
    create_time: TimeInfo
    update_time: TimeInfo
    display_time: TimeInfo
    content: str
    nodes: list
    visibility: int
    tags: list[str]
    property: dict
    snippet: str

# Define event classes with proper from_raw implementations
class MemoEvent(WebhookEventBase[MemoPayload]):
    """Base memo event class"""
    
    @classmethod
    def from_raw(
        cls,
        raw_data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        source_info: Optional[Dict[str, Any]] = None,
    ) -> "MemoEvent":
        """Override from_raw to properly handle MemoPayload"""
        headers = headers or {}
        source_info = source_info or {}
        
        # Transform raw data to match our payload structure
        payload_data = cls._transform_raw_data(raw_data)
        
        # Create typed payload
        payload = MemoPayload.model_validate(payload_data)
        
        return cls(payload=payload, headers=headers, source_info=source_info)
    
    def get_activity(self) -> str:
        # Use state to determine activity: 1=created, 2=updated, 3=deleted
        state_to_activity = {1: "created", 2: "updated", 3: "deleted"}
        return state_to_activity.get(self.payload.state, "unknown")

class MemoCreatedEvent(MemoEvent):
    """Specific event for memo creation"""
    
    @classmethod
    def matches(cls, raw_data: Dict[str, Any], headers: Dict[str, str] = None) -> bool:
        try:
            # Check if this is a creation event (state = 1)
            return raw_data.get('state') == 1
        except (KeyError, TypeError):
            return False

class MemoWithIdeaTagEvent(MemoEvent):
    """Event for memos with 'idea' tag"""
    
    @classmethod
    def matches(cls, raw_data: Dict[str, Any], headers: Dict[str, str] = None) -> bool:
        try:
            return 'idea' in raw_data.get('tags', [])
        except (KeyError, TypeError):
            return False

# Test handlers
class HandlerTracker:
    """Track which handlers were called"""
    def __init__(self):
        self.called_handlers = []
        self.called_triggers = []
    
    def reset(self):
        self.called_handlers.clear()
        self.called_triggers.clear()

tracker = HandlerTracker()

# Fixtures
@pytest.fixture
def event_bus():
    """Create a test event bus with registered handlers"""
    bus = EventBus(
        timeout_seconds=5.0,
        max_concurrent_handlers=10,
        swallow_exceptions=False,  # Don't swallow in tests
        enable_metrics=True
    )
    
    # Register pattern-based handlers
    @bus.on_pattern(MemoCreatedEvent)
    async def handle_memo_created(event: MemoCreatedEvent):
        tracker.called_handlers.append("pattern_memo_created")
    
    @bus.on_pattern(MemoWithIdeaTagEvent)
    async def handle_idea_memo(event: MemoWithIdeaTagEvent):
        tracker.called_handlers.append("pattern_idea_memo")
    
    # Register activity-based handlers
    @bus.on_activity("created")
    async def handle_created_activity(event):
        tracker.called_handlers.append("activity_created")
    
    @bus.on_activity("updated")
    async def handle_updated_activity(event):
        tracker.called_handlers.append("activity_updated")
    
    # Register catch-all handler
    @bus.on_any()
    async def handle_any_event(event):
        tracker.called_handlers.append("any_handler")
    
    return bus

@pytest.fixture(autouse=True)
def reset_tracker():
    """Reset handler tracker before each test"""
    tracker.reset()
    yield
    tracker.reset()

# Tests
class TestMemosWebhook:
    """Test memos webhook functionality"""
    
    @pytest.mark.asyncio
    async def test_memo_event_creation(self):
        """Test that memo events can be created from raw data"""
        event = MemoEvent.from_raw(MEMO_DATA_1)
        assert event.payload.name == MEMO_DATA_1['name']
        assert event.payload.state == MEMO_DATA_1['state']
        assert event.payload.tags == MEMO_DATA_1['tags']
    
    @pytest.mark.asyncio
    async def test_pattern_matching(self):
        """Test that pattern matching works correctly"""
        # Test memo creation pattern
        assert MemoCreatedEvent.matches(MEMO_DATA_1) is True
        assert MemoCreatedEvent.matches(MEMO_DATA_2) is True
        
        # Test idea tag pattern
        assert MemoWithIdeaTagEvent.matches(MEMO_DATA_1) is True
        assert MemoWithIdeaTagEvent.matches(MEMO_DATA_2) is True
        
        # Test with invalid data (should not match)
        invalid_data = {'state': 999, 'tags': []}
        assert MemoCreatedEvent.matches(invalid_data) is False
        assert MemoWithIdeaTagEvent.matches(invalid_data) is False
    
    @pytest.mark.asyncio
    async def test_activity_detection(self):
        """Test that activity detection works correctly"""
        event1 = MemoEvent.from_raw(MEMO_DATA_1)
        event2 = MemoEvent.from_raw(MEMO_DATA_2)
        
        # Both memos have state=1, which should be "created"
        assert event1.get_activity() == "created"
        assert event2.get_activity() == "created"
    
    @pytest.mark.asyncio
    async def test_pattern_based_handlers(self, event_bus):
        """Test pattern-based handler execution"""
        result = await event_bus.dispatch_raw(MEMO_DATA_1)
        
        # Should match both pattern handlers
        assert "pattern_memo_created" in tracker.called_handlers
        assert "pattern_idea_memo" in tracker.called_handlers
        assert result.success is True
    
    @pytest.mark.asyncio
    async def test_activity_based_handlers(self, event_bus):
        """Test activity-based handler execution"""
        result = await event_bus.dispatch_raw(MEMO_DATA_2)
        
        # Should match the "created" activity handler
        assert "activity_created" in tracker.called_handlers
        assert result.success is True
    
    @pytest.mark.asyncio
    async def test_end_to_end_processing(self, event_bus):
        """Test complete end-to-end processing"""
        # Process both memo examples
        result1 = await event_bus.dispatch_raw(MEMO_DATA_1)
        result2 = await event_bus.dispatch_raw(MEMO_DATA_2)
        
        # Both should succeed
        assert result1.success is True
        assert result2.success is True
        
        # Should match multiple patterns
        assert len(result1.matched_patterns) >= 2
        assert len(result2.matched_patterns) >= 2
        
        # Should execute multiple handlers
        assert result1.handler_count >= 2
        assert result2.handler_count >= 2
        
        # Check that specific handlers were called
        assert "pattern_memo_created" in tracker.called_handlers
        assert "pattern_idea_memo" in tracker.called_handlers
        assert "activity_created" in tracker.called_handlers
    
    @pytest.mark.asyncio
    async def test_processing_metrics(self, event_bus):
        """Test that processing metrics are collected"""
        # Process some events
        await event_bus.dispatch_raw(MEMO_DATA_1)
        await event_bus.dispatch_raw(MEMO_DATA_2)
        
        # Check metrics
        metrics = event_bus.get_metrics()
        assert metrics.total_events == 2
        assert metrics.successful_events == 2
        assert metrics.handler_executions >= 4  # At least 2 handlers per event
    
    @pytest.mark.asyncio
    async def test_invalid_data_fallback(self, event_bus):
        """Test that invalid data falls back to generic event"""
        invalid_data = {"invalid": "data"}
        
        result = await event_bus.dispatch_raw(invalid_data)
        
        # Should fall back to GenericWebhookEvent but still succeed
        assert result.success is True
        assert "GenericWebhookEvent" in result.matched_patterns
        
        # Should execute the catch-all handler
        assert "any_handler" in tracker.called_handlers

# Utility function to load test data from file
def load_test_data(filename: str) -> Dict[str, Any]:
    """Load test data from JSON file"""
    path = Path(__file__).parent / "test_data" / filename
    with open(path, 'r') as f:
        return json.load(f)
