"""End-to-end integration test with Memos API objects."""
from __future__ import annotations

import pytest
from typing import Dict, Any, List
from datetime import datetime

from pydantic import BaseModel, field_validator

from webhooky import EventBus, WebhookEventBase, on_activity, on_create, on_update


# Simplified models based on the memos project knowledge
class MemoNode(BaseModel):
    """Simplified memo node structure."""
    type: int
    Node: Dict[str, Any]


class MemoProperty(BaseModel):
    """Memo computed properties."""
    has_link: bool = False
    has_task_list: bool = False
    has_code: bool = False
    has_incomplete_tasks: bool = False


class MemoWebhookEvent(WebhookEventBase):
    """Base memo webhook event."""
    
    @field_validator('raw_data')
    @classmethod
    def validate_memo_data(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        required_fields = ['name', 'creator', 'content']
        if not all(field in v for field in required_fields):
            raise ValueError(f"Missing required memo fields: {required_fields}")
        return v
    
    @property
    def memo_name(self) -> str:
        return self.raw_data.get('name', '')
    
    @property
    def memo_id(self) -> str:
        """Extract memo ID from name (e.g., 'memos/kMfMonuFoFWFNCGT4q7Ssm' -> 'kMfMonuFoFWFNCGT4q7Ssm')."""
        name = self.memo_name
        return name.split('/')[-1] if '/' in name else name
    
    @property
    def creator(self) -> str:
        return self.raw_data.get('creator', '')
    
    @property
    def content(self) -> str:
        return self.raw_data.get('content', '')
    
    @property
    def tags(self) -> List[str]:
        return self.raw_data.get('tags', [])
    
    @property
    def visibility(self) -> int:
        return self.raw_data.get('visibility', 1)
    
    @property
    def has_tasks(self) -> bool:
        props = self.raw_data.get('property', {})
        return props.get('has_task_list', False)
    
    @property
    def has_incomplete_tasks(self) -> bool:
        props = self.raw_data.get('property', {})
        return props.get('has_incomplete_tasks', False)
    
    @property
    def create_timestamp(self) -> int:
        create_time = self.raw_data.get('create_time', {})
        return create_time.get('seconds', 0)


class MemoCreatedEvent(MemoWebhookEvent):
    """Memo creation event."""
    
    @classmethod
    def matches(cls, raw_data: Dict[str, Any], headers=None) -> bool:
        # Check if this is a memo with create/update times that are equal (new memo)
        if not all(field in raw_data for field in ['name', 'creator', 'content']):
            return False
        
        create_time = raw_data.get('create_time', {}).get('seconds', 0)
        update_time = raw_data.get('update_time', {}).get('seconds', 0)
        
        # New memos have equal create/update times
        return create_time == update_time and create_time > 0
    
    def get_activity(self) -> str:
        return 'created'
    
    @on_create()
    async def notify_new_memo(self):
        print(f"📝 New memo created: {self.memo_id}")
        print(f"   Creator: {self.creator}")
        print(f"   Content preview: {self.content[:50]}...")
        if self.tags:
            print(f"   Tags: {', '.join(self.tags)}")


class MemoWithTasksEvent(MemoWebhookEvent):
    """Memo with tasks/todos event."""
    
    @classmethod
    def matches(cls, raw_data: Dict[str, Any], headers=None) -> bool:
        if not super().matches(raw_data, headers):
            return False
        
        props = raw_data.get('property', {})
        return props.get('has_task_list', False)
    
    def get_activity(self) -> str:
        return 'task_memo'
    
    @on_activity('task_memo')
    async def handle_task_memo(self):
        task_status = "with incomplete tasks" if self.has_incomplete_tasks else "all tasks complete"
        print(f"✅ Task memo detected: {self.memo_id} ({task_status})")
        
        # Extract task items from content
        lines = self.content.split('\n')
        task_lines = [line.strip() for line in lines if line.strip().startswith('- [ ]') or line.strip().startswith('- [x]')]
        
        if task_lines:
            print(f"   Found {len(task_lines)} tasks:")
            for task in task_lines[:3]:  # Show first 3 tasks
                print(f"     {task}")


class MemoWithTagsEvent(MemoWebhookEvent):
    """Memo with specific tags event."""
    
    @classmethod
    def matches(cls, raw_data: Dict[str, Any], headers=None) -> bool:
        if not super().matches(raw_data, headers):
            return False
        
        tags = raw_data.get('tags', [])
        # Match memos with interesting tags
        interesting_tags = {'idea', 'project', 'important', 'todo'}
        return bool(set(tags) & interesting_tags)
    
    def get_activity(self) -> str:
        return 'tagged_memo'
    
    @on_activity('tagged_memo')
    async def process_tagged_memo(self):
        print(f"🏷️  Tagged memo: {self.memo_id}")
        print(f"   Tags: {', '.join(self.tags)}")
        
        # Special handling for different tag types
        if 'idea' in self.tags:
            print("   💡 Idea memo - added to idea collection")
        
        if 'project' in self.tags:
            print("   🚀 Project memo - notifying team")
        
        if 'important' in self.tags:
            print("   ⚠️  Important memo - flagged for attention")


# Test data from the examples provided
MEMO_SAMPLE_1 = {
    'name': 'memos/kMfMonuFoFWFNCGT4q7Ssm',
    'state': 1,
    'creator': 'users/1',
    'create_time': {'seconds': 1756837499},
    'update_time': {'seconds': 1756837499},
    'display_time': {'seconds': 1756837499},
    'content': '#idea testing an idea tag',
    'nodes': [
        {
            'type': 2,
            'Node': {
                'ParagraphNode': {
                    'children': [
                        {'type': 59, 'Node': {'TagNode': {'content': 'idea'}}},
                        {'type': 51, 'Node': {'TextNode': {'content': ' testing an idea tag'}}}
                    ]
                }
            }
        }
    ],
    'visibility': 1,
    'tags': ['idea'],
    'property': {},
    'snippet': '#idea testing an idea tag\n'
}

MEMO_SAMPLE_2 = {
    'name': 'memos/EZMx97CjKvre6h6jM7ouoC',
    'state': 1,
    'creator': 'users/1',
    'create_time': {'seconds': 1756838479},
    'update_time': {'seconds': 1756838479},
    'display_time': {'seconds': 1756838479},
    'content': "#idea #project But what if there's multiple tags?\n\n- even worse, lists?\n- [ ] heaven forbid todos...",
    'nodes': [
        {'type': 2, 'Node': {'ParagraphNode': {'children': [
            {'type': 59, 'Node': {'TagNode': {'content': 'idea'}}},
            {'type': 51, 'Node': {'TextNode': {'content': ' '}}},
            {'type': 59, 'Node': {'TagNode': {'content': 'project'}}},
            {'type': 51, 'Node': {'TextNode': {'content': " But what if there's multiple tags?"}}}
        ]}}},
        {'type': 1, 'Node': {'LineBreakNode': None}},
        {'type': 1, 'Node': {'LineBreakNode': None}},
        {'type': 7, 'Node': {'ListNode': {'kind': 2, 'children': [
            {'type': 9, 'Node': {'UnorderedListItemNode': {
                'symbol': '-',
                'children': [{'type': 51, 'Node': {'TextNode': {'content': 'even worse, lists?'}}}]
            }}},
            {'type': 1, 'Node': {'LineBreakNode': None}}
        ]}}},
        {'type': 7, 'Node': {'ListNode': {'kind': 3, 'children': [
            {'type': 10, 'Node': {'TaskListItemNode': {
                'symbol': '-',
                'children': [{'type': 51, 'Node': {'TextNode': {'content': 'heaven forbid todos...'}}}]
            }}}
        ]}}}
    ],
    'visibility': 1,
    'tags': ['idea', 'project'],
    'property': {'has_task_list': True, 'has_incomplete_tasks': True},
    'snippet': "#idea #project But what if there's multiple tags?\n\n-even worse, ..."
}


class TestMemosIntegration:
    """End-to-end tests with real Memos API data."""
    
    @pytest.mark.asyncio
    async def test_memo_creation_event(self):
        """Test memo creation detection and processing."""
        bus = EventBus()
        bus.register(MemoCreatedEvent)
        
        result = await bus.process_webhook(MEMO_SAMPLE_1)
        
        assert result.success
        assert 'MemoCreatedEvent' in result.matched_patterns
        assert len(result.triggered_methods) >= 1
        assert 'MemoCreatedEvent.notify_new_memo' in result.triggered_methods
    
    @pytest.mark.asyncio
    async def test_memo_with_tasks_event(self):
        """Test memo with tasks detection."""
        bus = EventBus()
        bus.register(MemoWithTasksEvent)
        
        result = await bus.process_webhook(MEMO_SAMPLE_2)
        
        assert result.success
        assert 'MemoWithTasksEvent' in result.matched_patterns
        assert 'MemoWithTasksEvent.handle_task_memo' in result.triggered_methods
    
    @pytest.mark.asyncio
    async def test_memo_with_tags_event(self):
        """Test tagged memo detection."""
        bus = EventBus()
        bus.register(MemoWithTagsEvent)
        
        # Test both samples (both have interesting tags)
        result1 = await bus.process_webhook(MEMO_SAMPLE_1)
        result2 = await bus.process_webhook(MEMO_SAMPLE_2)
        
        assert result1.success and result2.success
        assert 'MemoWithTagsEvent' in result1.matched_patterns
        assert 'MemoWithTagsEvent' in result2.matched_patterns
    
    @pytest.mark.asyncio
    async def test_multiple_event_matching(self):
        """Test that a single memo can match multiple event types."""
        bus = EventBus()
        bus.register_all(MemoCreatedEvent, MemoWithTasksEvent, MemoWithTagsEvent)
        
        # MEMO_SAMPLE_2 should match all three patterns
        result = await bus.process_webhook(MEMO_SAMPLE_2)
        
        assert result.success
        assert len(result.matched_patterns) >= 2  # Should match multiple patterns
        assert 'MemoCreatedEvent' in result.matched_patterns
        assert 'MemoWithTasksEvent' in result.matched_patterns
        assert 'MemoWithTagsEvent' in result.matched_patterns
    
    @pytest.mark.asyncio
    async def test_memo_property_extraction(self):
        """Test property extraction from memo objects."""
        bus = EventBus()
        bus.register(MemoCreatedEvent)
        
        result = await bus.process_webhook(MEMO_SAMPLE_1)
        
        # Verify we can create event and extract properties
        assert result.success
        
        # Test property extraction by creating event directly
        event = MemoCreatedEvent.from_raw(MEMO_SAMPLE_1)
        assert event.memo_id == 'kMfMonuFoFWFNCGT4q7Ssm'
        assert event.creator == 'users/1'
        assert event.content == '#idea testing an idea tag'
        assert event.tags == ['idea']
        assert event.create_timestamp == 1756837499
        assert not event.has_tasks
    
    @pytest.mark.asyncio
    async def test_memo_with_complex_structure(self):
        """Test memo with complex nodes structure."""
        bus = EventBus()
        bus.register(MemoWithTasksEvent)
        
        result = await bus.process_webhook(MEMO_SAMPLE_2)
        
        assert result.success
        
        # Test complex property extraction
        event = MemoWithTasksEvent.from_raw(MEMO_SAMPLE_2)
        assert event.memo_id == 'EZMx97CjKvre6h6jM7ouoC'
        assert event.tags == ['idea', 'project']
        assert event.has_tasks
        assert event.has_incomplete_tasks
        assert 'multiple tags' in event.content
        assert '- [ ]' in event.content  # Has task syntax
    
    @pytest.mark.asyncio
    async def test_webhook_header_processing(self):
        """Test processing with webhook headers."""
        bus = EventBus()
        bus.register(MemoCreatedEvent)
        
        headers = {
            'user-agent': 'Memos-Webhook/1.0',
            'content-type': 'application/json',
            'x-memo-event': 'memo.created'
        }
        
        result = await bus.process_webhook(
            MEMO_SAMPLE_1,
            headers=headers,
            source_info={'webhook_source': 'memos_api'}
        )
        
        assert result.success
        assert result.headers == headers
        
        # Verify event has access to headers and source info
        event = MemoCreatedEvent.from_raw(
            MEMO_SAMPLE_1,
            headers=headers,
            source_info={'webhook_source': 'memos_api'}
        )
        assert event.headers['user-agent'] == 'Memos-Webhook/1.0'
        assert event.source_info['webhook_source'] == 'memos_api'
    
    @pytest.mark.asyncio
    async def test_invalid_memo_data(self):
        """Test handling of invalid memo data."""
        bus = EventBus(fallback_to_generic=True)
        bus.register(MemoCreatedEvent)
        
        # Invalid memo data (missing required fields)
        invalid_data = {'name': 'memos/invalid', 'some_field': 'value'}
        
        result = await bus.process_webhook(invalid_data)
        
        assert result.success  # Should fallback to generic
        assert 'GenericWebhookEvent' in result.matched_patterns
        assert 'MemoCreatedEvent' not in result.matched_patterns
    
    @pytest.mark.asyncio
    async def test_performance_with_multiple_patterns(self):
        """Test performance with multiple registered patterns."""
        bus = EventBus()
        bus.register_all(MemoCreatedEvent, MemoWithTasksEvent, MemoWithTagsEvent)
        
        # Process both samples multiple times
        for _ in range(3):
            result1 = await bus.process_webhook(MEMO_SAMPLE_1)
            result2 = await bus.process_webhook(MEMO_SAMPLE_2)
            
            assert result1.success and result2.success
            assert result1.processing_time < 1.0  # Should be fast
            assert result2.processing_time < 1.0
        
        # Check final stats
        stats = bus.get_stats()
        assert stats['total_processed'] == 6
        assert stats['total_matches'] >= 6  # At least one match per webhook
        assert stats['total_errors'] == 0
