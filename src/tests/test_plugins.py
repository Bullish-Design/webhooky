import pytest
import sys
from pathlib import Path

from webhooky.plugins import plugin_manager, webhook_handler
from webhooky.bus import EventBus
from webhooky.events import WebhookEventBase

PLUGIN_CONTENT = """
from webhooky.plugins import webhook_handler
from webhooky.events import WebhookEventBase

class PluginEvent(WebhookEventBase):
    payload: dict
    @classmethod
    def matches(cls, raw_data, headers=None):
        return "plugin_event" in raw_data

@webhook_handler(pattern=PluginEvent)
def handle_plugin_event(event):
    pass

@webhook_handler(activity="plugin_activity")
async def handle_plugin_activity(event):
    pass
"""

def test_load_directory_plugins(create_plugin_file):
    """Test loading a plugin from a file in a directory."""
    _create, plugins_dir = create_plugin_file
    _create("my_plugin.py", PLUGIN_CONTENT)

    # Add plugin dir to path so import can work
    sys.path.insert(0, str(plugins_dir.parent))

    results = plugin_manager.load_directory_plugins(plugins_dir)
    assert results == {"my_plugin": True}
    
    loaded_plugins = plugin_manager.get_loaded_plugins()
    assert "my_plugin" in loaded_plugins
    
    info = plugin_manager.get_plugin_info("my_plugin")
    assert info.loaded is True
    assert "PluginEvent" in info.event_classes
    assert "handle_plugin_event" in info.handlers
    assert "handle_plugin_activity" in info.handlers

    sys.path.pop(0)

@pytest.mark.asyncio
async def test_plugin_handler_registration(create_plugin_file, test_bus: EventBus):
    """Test that loaded plugin handlers are correctly registered with the bus."""
    _create, plugins_dir = create_plugin_file
    _create("my_plugin_2.py", PLUGIN_CONTENT)
    sys.path.insert(0, str(plugins_dir.parent))

    plugin_manager.load_directory_plugins(plugins_dir)
    plugin_manager.register_with_bus(test_bus)

    counts = test_bus.get_handler_count()
    assert counts["pattern_handlers"] == 1
    assert counts["activity_handlers"] == 1

    # Test that dispatching triggers the plugin handlers
    pattern_payload = {"plugin_event": True}
    activity_payload = {"action": "plugin_activity"}

    # We need a dummy event for the activity handler to match against
    class GenericForActivity(WebhookEventBase):
        payload: dict
        def get_activity(self): return self.payload.get("action")
    
    # Manually dispatch a pre-made event to test the activity handler
    activity_event = GenericForActivity(payload=activity_payload)

    result1 = await test_bus.dispatch_raw(pattern_payload)
    result2 = await test_bus.dispatch_event(activity_event)

    assert result1.success and result1.handler_count == 1
    assert result2.success and result2.handler_count == 1
    
    sys.path.pop(0)
