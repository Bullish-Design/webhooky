import pytest
from pydantic import BaseModel, Field

from webhooky.events import WebhookEventBase, on_activity
from webhooky.registry import event_registry
from webhooky.bus import EventBus

# --- Test Event Models ---
class User(BaseModel):
    id: int
    name: str

class PullRequestPayload(BaseModel):
    action: str
    number: int
    user: User

class PullRequestEvent(WebhookEventBase[PullRequestPayload]):
    """An event for GitHub Pull Requests."""
    triggered_methods: list = Field(default_factory=list, exclude=True)

    @classmethod
    def matches(cls, raw_data, headers=None):
        return "pull_request" in raw_data

    @classmethod
    def _transform_raw_data(cls, raw_data):
        # Simulate extracting the relevant part of a larger payload
        return raw_data.get("pull_request", {})

    @on_activity("opened")
    async def on_pr_opened(self):
        self.triggered_methods.append("on_pr_opened")

    @on_activity("closed")
    def on_pr_closed(self):
        self.triggered_methods.append("on_pr_closed")

def test_event_registry_auto_registration():
    class LocalPullRequestEvent(WebhookEventBase):
        pass
    """Test that subclassing WebhookEventBase automatically registers the class."""
    assert "LocalPullRequestEvent" in event_registry.get_registry_info().registered_classes
    assert event_registry.get_event_class("PullRequestEvent") is PullRequestEvent

def test_event_matches_and_from_raw():
    """Test the pattern matching and data transformation logic."""
    raw_data = {
        "pull_request": {
            "action": "opened",
            "number": 42,
            "user": {"id": 1, "name": "test-user"}
        }
    }
    assert PullRequestEvent.matches(raw_data) is True
    event = PullRequestEvent.from_raw(raw_data)
    assert isinstance(event, PullRequestEvent)
    assert isinstance(event.payload, PullRequestPayload)
    assert event.payload.number == 42
    assert event.payload.user.name == "test-user"

def test_event_does_not_match():
    """Test that non-matching data returns False."""
    raw_data = {"issue": {"action": "opened"}}
    assert PullRequestEvent.matches(raw_data) is False

@pytest.mark.asyncio
async def test_event_internal_triggers():
    """Test that methods decorated with @on_activity are called."""
    opened_payload = {"pull_request": {"action": "opened", "number": 1, "user": {"id": 1, "name": "a"}}}
    closed_payload = {"pull_request": {"action": "closed", "number": 2, "user": {"id": 1, "name": "a"}}}

    opened_event = PullRequestEvent.from_raw(opened_payload)
    closed_event = PullRequestEvent.from_raw(closed_payload)

    # Process triggers
    opened_triggered = await opened_event.process_triggers()
    closed_triggered = await closed_event.process_triggers()

    assert opened_triggered == ["PullRequestEvent.on_pr_opened"]
    assert opened_event.triggered_methods == ["on_pr_opened"]

    assert closed_triggered == ["PullRequestEvent.on_pr_closed"]
    assert closed_event.triggered_methods == ["on_pr_closed"]

@pytest.mark.asyncio
async def test_event_internal_triggers_on_bus_dispatch():
    """Ensure internal triggers are fired during a normal bus dispatch."""
    bus = EventBus()
    opened_payload = {"pull_request": {"action": "opened", "number": 1, "user": {"id": 1, "name": "a"}}}

    # The result from dispatch_event includes the triggered method names
    result = await bus.dispatch_event(PullRequestEvent.from_raw(opened_payload))

    assert result.success
    assert result.triggered_methods == ["PullRequestEvent.on_pr_opened"]
