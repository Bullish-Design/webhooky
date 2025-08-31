#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "webhooky",
#   "pydantic>=2.7",
# ]
# ///

"""WebHooky usage examples demonstrating core functionality."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

from pydantic import BaseModel, field_validator

# Import WebHooky components
from webhooky import (
    EventBus,
    WebhookEventBase,
    GenericWebhookEvent,
    on_create,
    on_update,
    on_activity,
    create_dev_config,
)


# Example 1: Basic pattern-based event processing
class GitHubPushPayload(BaseModel):
    """GitHub push event payload."""
    ref: str
    repository: Dict[str, Any]
    commits: list[Dict[str, Any]]
    
    @field_validator('ref')
    @classmethod
    def validate_ref(cls, v: str) -> str:
        if not v.startswith('refs/'):
            raise ValueError('Must be a valid git ref')
        return v


class GitHubPushEvent(WebhookEventBase[GitHubPushPayload]):
    """GitHub push webhook event with validation-based matching."""
    
    @classmethod
    def _transform_raw_data(cls, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant data for GitHub push events."""
        # Only match if this looks like a GitHub push
        if 'ref' not in raw_data or 'repository' not in raw_data:
            raise ValueError("Not a GitHub push event")
        return raw_data
    
    @on_create()
    async def handle_push(self):
        """Trigger method for push events."""
        repo_name = self.payload.repository.get('name', 'unknown')
        commit_count = len(self.payload.commits)
        print(f"📦 Push to {repo_name}: {commit_count} commits")


# Example 2: Simple memo event with content validation
class MemoPayload(BaseModel):
    """Memo payload with content validation."""
    name: str
    content: str
    tags: list[str] = []
    
    @field_validator('content')
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('Content cannot be empty')
        return v.strip()


class MemoEvent(WebhookEventBase[MemoPayload]):
    """Memo event with automatic categorization."""
    
    @classmethod
    def _transform_raw_data(cls, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract memo data from various webhook structures."""
        # Handle nested memo structure
        if 'memo' in raw_data:
            return raw_data['memo']
        # Handle direct structure  
        if 'name' in raw_data and 'content' in raw_data:
            return raw_data
        raise ValueError("Not a memo event")
    
    @on_activity('create', 'new', 'add')
    async def process_memo(self):
        """Process new memo."""
        print(f"📝 New memo: {self.payload.name}")
        if 'urgent' in self.payload.tags:
            print("🚨 URGENT memo detected!")


# Example 3: Complex validation with multiple checks
class UrgentNotificationPayload(BaseModel):
    """Urgent notification with strict validation."""
    priority: str
    message: str
    recipients: list[str]
    
    @field_validator('priority')
    @classmethod
    def must_be_urgent(cls, v: str) -> str:
        if v.lower() not in ['urgent', 'critical', 'high']:
            raise ValueError('Not an urgent notification')
        return v.lower()
    
    @field_validator('recipients')
    @classmethod
    def has_recipients(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError('Must have recipients')
        return v


class UrgentNotificationEvent(WebhookEventBase[UrgentNotificationPayload]):
    """Only matches truly urgent notifications."""
    
    @on_activity('alert', 'urgent', 'critical')
    async def send_alert(self):
        """Send urgent alert."""
        recipient_count = len(self.payload.recipients)
        print(f"🚨 URGENT: {self.payload.message} (→ {recipient_count} recipients)")


async def example_basic_usage():
    """Example 1: Basic WebHooky usage."""
    print("\n=== Example 1: Basic Usage ===")
    
    # Create event bus
    bus = EventBus(timeout_seconds=10.0, swallow_exceptions=False)
    
    # Register handlers using decorators
    @bus.on_pattern(GitHubPushEvent)
    async def handle_github_push(event: GitHubPushEvent):
        """Handler for GitHub push events."""
        repo = event.payload.repository.get('full_name', 'unknown')
        branch = event.payload.ref.split('/')[-1]
        print(f"🔄 Processing push to {repo}:{branch}")
    
    @bus.on_pattern(MemoEvent)
    async def handle_memo(event: MemoEvent):
        """Handler for memo events.""" 
        word_count = len(event.payload.content.split())
        print(f"📄 Processing memo '{event.payload.name}' ({word_count} words)")
    
    # Process some test events
    test_events = [
        # GitHub push event
        {
            "ref": "refs/heads/main",
            "repository": {"name": "my-repo", "full_name": "user/my-repo"},
            "commits": [{"id": "abc123", "message": "Fix bug"}]
        },
        # Memo event
        {
            "memo": {
                "name": "meeting-notes",
                "content": "Discussed webhook processing architecture",
                "tags": ["meeting", "architecture"]
            }
        },
        # Event that doesn't match any pattern
        {
            "unknown_type": "test",
            "data": "This won't match any specific pattern"
        }
    ]
    
    for raw_data in test_events:
        print(f"\nProcessing: {json.dumps(raw_data, indent=2)[:50]}...")
        result = await bus.dispatch_raw(raw_data)
        print(f"Result: {result.matched_patterns} (success: {result.success})")


async def example_activity_routing():
    """Example 2: Activity-based routing."""
    print("\n=== Example 2: Activity-Based Routing ===")
    
    # Create bus with activity groups
    activity_groups = {
        "crud": {"create", "update", "delete"},
        "github": {"push", "pull_request", "issue"}
    }
    bus = EventBus(activity_groups=activity_groups)
    
    # Register activity handlers
    @bus.on_group("crud")
    async def handle_crud_operations(event):
        """Handle any CRUD operation."""
        activity = event.get_activity()
        print(f"🔧 CRUD operation: {activity}")
    
    @bus.on_activity("create")
    async def handle_creation(event):
        """Handle creation events specifically."""
        print(f"➕ New item created: {event.__class__.__name__}")
    
    # Test with raw events that have activity indicators
    test_data = [
        {"action": "create", "item": "document"},
        {"event": "update", "item": "profile"},  
        {"type": "push", "repo": "my-repo"},
        {"activity": "delete", "item": "account"}
    ]
    
    for data in test_data:
        result = await bus.dispatch_raw(data)
        print(f"Processed {data} → {result.handler_count} handlers")


async def example_plugin_system():
    """Example 3: Plugin system demonstration."""
    print("\n=== Example 3: Plugin System ===")
    
    from webhooky import plugin_manager, event_registry
    
    # Show discovered plugins
    discovered = plugin_manager.discover_plugins()
    print(f"Discovered plugins: {discovered}")
    
    # Show registered event classes
    registry_info = event_registry.get_registry_info()
    print(f"Registered event classes: {registry_info.registered_classes}")
    
    # Show validation stats
    print("Validation statistics:")
    for class_name, stats in registry_info.validation_stats.items():
        print(f"  {class_name}: {stats}")


async def example_error_handling():
    """Example 4: Error handling and recovery."""
    print("\n=== Example 4: Error Handling ===")
    
    bus = EventBus(swallow_exceptions=True, enable_metrics=True)
    
    @bus.on_any()
    async def failing_handler(event):
        """Handler that sometimes fails."""
        if "fail" in str(event.payload):
            raise ValueError("Simulated handler failure")
        print(f"✅ Successfully processed: {event.__class__.__name__}")
    
    @bus.on_any() 
    async def logging_handler(event):
        """Handler that logs all events."""
        print(f"📊 Logged event: {event.__class__.__name__}")
    
    # Test with good and bad data
    test_data = [
        {"message": "good event"},
        {"message": "fail this event"},  # Will cause failure
        {"message": "another good event"}
    ]
    
    for data in test_data:
        result = await bus.dispatch_raw(data)
        print(f"Result: success={result.success}, errors={len(result.errors)}")
    
    # Show metrics
    metrics = bus.get_metrics()
    print(f"\nMetrics: {metrics.success_rate:.1%} success rate")
    print(f"Total events: {metrics.total_events}")
    print(f"Failed events: {metrics.failed_events}")


async def example_smeeme_integration():
    """Example 5: SmeeMe integration pattern."""
    print("\n=== Example 5: SmeeMe Integration Pattern ===")
    
    # This shows how you would integrate with SmeeMe
    # (actual SmeeMe import commented to avoid dependency)
    
    from webhooky.adapters.smeeme import SmeeEventAdapter
    
    # Create WebHooky bus
    bus = EventBus()
    
    # Create adapter
    adapter = SmeeEventAdapter(bus)
    
    # Create workflow handler for SmeeMe
    workflow_handler = adapter.create_workflow_handler()
    
    print("Created SmeeMe workflow handler")
    print("To use: smee_instance.register_workflow('webhooky', workflow_handler)")
    
    # Simulate what SmeeMe would do
    class MockSmeeEvent:
        def __init__(self, data):
            self.headers = {"content-type": "application/json"}
            self.body = data
            self.timestamp = 1234567890
            self.source_ip = "127.0.0.1"
            
        def get_json_body(self):
            return self.body
    
    class MockWorkflowJob:
        def __init__(self, event):
            self.event = event
    
    # Test the adapter
    mock_smee_event = MockSmeeEvent({"name": "test-memo", "content": "Hello from SmeeMe"})
    mock_job = MockWorkflowJob(mock_smee_event)
    
    result = workflow_handler(mock_job)
    print(f"Adapter result: {json.dumps(result, indent=2)}")


async def main():
    """Run all examples."""
    print("WebHooky Examples")
    print("=" * 50)
    
    await example_basic_usage()
    await example_activity_routing()
    await example_plugin_system()
    await example_error_handling()
    await example_smeeme_integration()
    
    print("\n✅ All examples completed!")


if __name__ == "__main__":
    asyncio.run(main())