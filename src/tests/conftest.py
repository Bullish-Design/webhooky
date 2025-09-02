import pytest
import pytest_asyncio
import asyncio
from pathlib import Path
import json
from typing import Dict, Any, List

from webhooky.bus import EventBus
from webhooky.plugins import plugin_manager
from webhooky.registry import event_registry

@pytest.fixture(scope="function", autouse=True)
def reset_singletons():
    """Ensure singletons are reset for each test function."""
    # This is crucial to prevent state leakage between tests
    plugin_manager.__init__()
    event_registry.__init__()
    yield

@pytest_asyncio.fixture
async def test_bus() -> EventBus:
    """Provides a default EventBus instance for testing."""
    return EventBus(swallow_exceptions=False, enable_metrics=True, timeout_seconds=1.0)

@pytest.fixture
def sample_payload() -> Dict[str, Any]:
    """Provides a generic webhook payload."""
    return {"event": "test", "user": "tester", "data": {"id": 123, "value": "abc"}}

@pytest.fixture
def create_plugin_file(tmp_path: Path):
    """A factory fixture to create temporary plugin files."""
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()

    def _create(filename: str, content: str):
        plugin_file = plugins_dir / filename
        plugin_file.write_text(content)
        return plugin_file

    return _create, plugins_dir
