import pytest
import asyncio
import json
import sys
import logging
from pathlib import Path
from typing import List, Dict, Any, Union, Optional

from pydantic import BaseModel, Field

from webhooky.bus import EventBus
from webhooky.events import WebhookEventBase, on_activity
from webhooky.plugins import plugin_manager, webhook_handler


logger = logging.getLogger(__name__)
# --- 1. Pydantic Models for the "Memos" Webhook Payload ---

class TimeObject(BaseModel):
    seconds: int

# Define Node types for discriminated union
class ParagraphNode(BaseModel):
    children: List["Node"]

class TagNode(BaseModel):
    content: str

class TextNode(BaseModel):
    content: str

class LineBreakNode(BaseModel):
    pass  # No fields needed

class TaskListItemNode(BaseModel):
    symbol: str
    children: List["Node"]

class UnorderedListItemNode(BaseModel):
    symbol: str
    children: List["Node"]

class ListNode(BaseModel):
    kind: int
    children: List["Node"]

class NodeContent(BaseModel):
    ParagraphNode: Optional[ParagraphNode] = None
    TagNode: Optional[TagNode] = None
    TextNode: Optional[TextNode] = None
    LineBreakNode: Optional[LineBreakNode] = None
    TaskListItemNode: Optional[TaskListItemNode] = None
    UnorderedListItemNode: Optional[UnorderedListItemNode] = None
    ListNode: Optional[ListNode] = None

class Node(BaseModel):
    type: int
    Node: NodeContent

# Resolve forward references
ParagraphNode.model_rebuild() #update_forward_refs(Node=Node)
TaskListItemNode.model_rebuild() #.update_forward_refs(Node=Node)
UnorderedListItemNode.model_rebuild() #.update_forward_refs(Node=Node)
ListNode.model_rebuild() #.update_forward_refs(Node=Node)


class MemoPayload(BaseModel):
    name: str
    state: int
    creator: str
    create_time: TimeObject
    update_time: TimeObject
    content: str
    nodes: List[Node]
    tags: List[str]
    property: Dict[str, Any]

# --- 2. Custom Webhooky Event Class for Memos ---

# A global list to track calls to internal triggers
INTERNAL_TRIGGER_CALLS = []

class MemoEvent(WebhookEventBase[MemoPayload]):
    """Represents a webhook event from a 'memos' application."""

    @classmethod
    def matches(cls, raw_data: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> bool:
        # A memo is identified by having 'creator' and 'create_time' fields.
        return "creator" in raw_data and "create_time" in raw_data

    def get_activity(self) -> Optional[str]:
        # Determine if it's a new memo or an updated one
        if self.payload.create_time.seconds == self.payload.update_time.seconds:
            return "create"
        return "update"

    @on_activity("create")
    async def on_new_memo(self):
        """Internal trigger for any newly created memo."""
        INTERNAL_TRIGGER_CALLS.append(f"new_memo:{self.payload.name}")

    @on_activity("create", "update")
    def on_project_memo(self):
        """Internal trigger that fires if 'project' tag is present."""
        if "project" in self.payload.tags:
            INTERNAL_TRIGGER_CALLS.append(f"project_memo:{self.payload.name}")


# --- 3. Mock Plugin with Handlers ---

MEMO_PLUGIN_CONTENT = """
from webhooky.plugins import webhook_handler
from tests.test_e2e_memos import MemoEvent # Import from test file

# Using lists to track handler calls across processes if needed, simple vars are fine here
PATTERN_HANDLER_CALLS = []
ACTIVITY_HANDLER_CALLS = []
ANY_HANDLER_CALLS = []

@webhook_handler(pattern=MemoEvent)
def handle_memo_by_pattern(event: MemoEvent):
    '''This handler triggers ONLY for MemoEvent instances.'''
    PATTERN_HANDLER_CALLS.append(event.payload.name)

@webhook_handler(activity="create")
async def handle_memo_creation_activity(event: MemoEvent):
    '''This handler triggers for any event with a 'create' activity.'''
    ACTIVITY_HANDLER_CALLS.append(event.payload.name)

@webhook_handler()
def handle_any_event(event):
    '''This is a catch-all handler that runs for every event.'''
    ANY_HANDLER_CALLS.append(event.__class__.__name__)
"""

# --- 4. The End-to-End Test ---

@pytest.fixture
def memo_payloads(tmp_path: Path) -> Path:
    """Fixture to write the sample memo payloads to a JSON file."""
    payloads = [
        {'name': 'memos/kMfMonuFoFWFNCGT4q7Ssm', 'state': 1, 'creator': 'users/1', 'create_time': {'seconds': 1756837499}, 'update_time': {'seconds': 1756837499}, 'display_time': {'seconds': 1756837499}, 'content': '#idea testing an idea tag', 'nodes': [{'type': 2, 'Node': {'ParagraphNode': {'children': [{'type': 59, 'Node': {'TagNode': {'content': 'idea'}}}, {'type': 51, 'Node': {'TextNode': {'content': ' testing an idea tag'}}}]}}}], 'visibility': 1, 'tags': ['idea'], 'property': {}, 'snippet': '#idea testing an idea tag\n'},
        {'name': 'memos/EZMx97CjKvre6h6jM7ouoC', 'state': 1, 'creator': 'users/1', 'create_time': {'seconds': 1756838479}, 'update_time': {'seconds': 1756838479}, 'display_time': {'seconds': 1756838479}, 'content': "#idea #project But what if there's multiple tags?\n\n- even worse, lists?\n- [ ] heaven forbid todos...", 'nodes': [{'type': 2, 'Node': {'ParagraphNode': {'children': [{'type': 59, 'Node': {'TagNode': {'content': 'idea'}}}, {'type': 51, 'Node': {'TextNode': {'content': ' '}}}, {'type': 59, 'Node': {'TagNode': {'content': 'project'}}}, {'type': 51, 'Node': {'TextNode': {'content': " But what if there's multiple tags?"}}}]}}}, {'type': 1, 'Node': {'LineBreakNode': None}}, {'type': 1, 'Node': {'LineBreakNode': None}}, {'type': 7, 'Node': {'ListNode': {'kind': 2, 'children': [{'type': 9, 'Node': {'UnorderedListItemNode': {'symbol': '-', 'children': [{'type': 51, 'Node': {'TextNode': {'content': 'even worse, lists?'}}}]}}}, {'type': 1, 'Node': {'LineBreakNode': None}}]}}}, {'type': 7, 'Node': {'ListNode': {'kind': 3, 'children': [{'type': 10, 'Node': {'TaskListItemNode': {'symbol': '-', 'children': [{'type': 51, 'Node': {'TextNode': {'content': 'heaven forbid todos...'}}}]}}}]}}}], 'visibility': 1, 'tags': ['idea', 'project'], 'property': {'has_task_list': True, 'has_incomplete_tasks': True}, 'snippet': "#idea #project But what if there's multiple tags?\n\n-even worse, ..."},
        {'event_type': 'some_other_event', 'details': 'This should not match MemoEvent'}
    ]
    payload_file = tmp_path / "memos_payloads.json"
    payload_file.write_text(json.dumps(payloads))
    return payload_file

@pytest.mark.asyncio
async def test_memos_e2e_processing(create_plugin_file, memo_payloads: Path):
    """
    This test orchestrates the entire webhooky flow:
    1. Defines custom Pydantic models and a MemoEvent class.
    2. Creates a plugin file with pattern, activity, and catch-all handlers.
    3. Loads webhook data from a file.
    4. Initializes and configures the EventBus and PluginManager.
    5. Dispatches the events.
    6. Asserts that the correct events were matched, handlers were called,
       and internal triggers were fired.
    """
    # -- Setup --
    _create, plugins_dir = create_plugin_file
    logger.info(f"Plugins directory: {plugins_dir}")
    _create("memos_plugin.py", MEMO_PLUGIN_CONTENT)
    # Add the current test directory to the path so the plugin can import MemoEvent
    sys.path.insert(0, str(Path(__file__).parent))

    # Clear global state from previous runs
    INTERNAL_TRIGGER_CALLS.clear()

    # Load payloads from the file created by the fixture
    payloads_data = json.loads(memo_payloads.read_text())

    # Create and configure the bus
    bus = EventBus(swallow_exceptions=False)
    plugin_manager.load_directory_plugins(plugins_dir)
    plugin_manager.register_with_bus(bus)

    # -- Execution --
    tasks = [bus.dispatch_raw(p) for p in payloads_data]
    results = await asyncio.gather(*tasks)

    # -- Assertions --

    # Import the plugin module to inspect its state
    from webhooky.plugins import memos_plugin

    # 1. Assert Processing Results
    assert len(results) == 3
    assert results[0].success is True
    assert results[1].success is True
    assert results[2].success is True

    # 2. Assert Pattern Matching
    assert results[0].matched_patterns == ["MemoEvent"]
    assert results[1].matched_patterns == ["MemoEvent"]
    assert results[2].matched_patterns == ["GenericWebhookEvent"] # The non-memo payload

    # 3. Assert Plugin Handler Calls
    assert len(memos_plugin.PATTERN_HANDLER_CALLS) == 2
    assert "memos/kMfMonuFoFWFNCGT4q7Ssm" in memos_plugin.PATTERN_HANDLER_CALLS
    assert "memos/EZMx97CjKvre6h6jM7ouoC" in memos_plugin.PATTERN_HANDLER_CALLS

    assert len(memos_plugin.ACTIVITY_HANDLER_CALLS) == 2
    assert "memos/kMfMonuFoFWFNCGT4q7Ssm" in memos_plugin.ACTIVITY_HANDLER_CALLS
    assert "memos/EZMx97CjKvre6h6jM7ouoC" in memos_plugin.ACTIVITY_HANDLER_CALLS

    assert len(memos_plugin.ANY_HANDLER_CALLS) == 3
    assert memos_plugin.ANY_HANDLER_CALLS.count("MemoEvent") == 2
    assert memos_plugin.ANY_HANDLER_CALLS.count("GenericWebhookEvent") == 1

    # 4. Assert Internal Event Trigger Calls
    assert len(INTERNAL_TRIGGER_CALLS) == 3
    assert "new_memo:memos/kMfMonuFoFWFNCGT4q7Ssm" in INTERNAL_TRIGGER_CALLS
    assert "new_memo:memos/EZMx97CjKvre6h6jM7ouoC" in INTERNAL_TRIGGER_CALLS
    assert "project_memo:memos/EZMx97CjKvre6h6jM7ouoC" in INTERNAL_TRIGGER_CALLS

    # -- Teardown --
    sys.path.pop(0)
