# WebHooky

Validation-based webhook event processing with explicit bus architecture. Combines the best of both worlds: Hooky's explicit bus + strong typing with Hookshot's validation-based pattern matching.

## Features

- **Validation-as-Pattern-Matching** – Event classes define what they match through Pydantic validation
- **Explicit Bus Architecture** – Testable, injectable EventBus with timeout handling
- **Strong Generic Typing** – `WebhookEventBase[PayloadT]` for type-safe event processing
- **Async-First Design** – Built for high-performance concurrent webhook processing
- **Plugin System** – Extensible via entry points with lifecycle management
- **FastAPI Integration** – Drop-in webhook endpoints with status/metrics routes
- **Comprehensive Observability** – Built-in metrics, logging, and introspection
- **SmeeMe Compatible** – Works seamlessly with SmeeMe webhook tunneling

## Installation

```bash
# Basic installation
uv add webhooky

# With FastAPI support
uv add webhooky[fastapi]

# With CLI tools
uv add webhooky[cli]

# With SmeeMe integration
uv add webhooky[smeeme]

# Everything
uv add webhooky[all]
```

## Quick Start

### Basic Usage

```python
from pydantic import BaseModel, field_validator
from webhooky import EventBus, WebhookEventBase, on_create

# Define typed payload
class GitHubPushPayload(BaseModel):
    ref: str
    repository: dict
    
    @field_validator('ref')
    @classmethod
    def validate_ref(cls, v: str) -> str:
        if not v.startswith('refs/'):
            raise ValueError('Invalid git ref')
        return v

# Define event pattern
class GitHubPushEvent(WebhookEventBase[GitHubPushPayload]):
    @on_create()
    async def handle_push(self):
        repo = self.payload.repository.get('name')
        print(f"Push to {repo}")

# Create bus and register handler
bus = EventBus()

@bus.on_pattern(GitHubPushEvent)
async def process_push(event: GitHubPushEvent):
    print(f"Processing: {event.payload.ref}")

# Process webhook
result = await bus.dispatch_raw({
    "ref": "refs/heads/main",
    "repository": {"name": "my-repo"}
})
```

### FastAPI Integration

```python
from webhooky.fastapi import create_app

# Create webhook processing server
app = create_app()

# Auto-generated routes:
# POST /webhooks/webhook - Process webhooks
# GET /webhooks/status - System status
# GET /webhooks/test - Testing endpoints
# GET /health - Health check

# Run with: uvicorn app:app
```

### CLI Usage

```bash
# Start webhook server
webhooky serve --host 0.0.0.0 --port 8000

# Test webhook processing
webhooky test --json '{"type": "test", "data": "hello"}'

# Validate payload against patterns
webhooky validate payload.json

# Show system status
webhooky status --format table

# Manage plugins  
webhooky plugins list
webhooky plugins load my-plugin
```

## Core Concepts

### Pattern Definition

Events define what they match through Pydantic validation:

```python
class UrgentEventPayload(BaseModel):
    priority: str
    message: str
    
    @field_validator('priority') 
    @classmethod
    def must_be_urgent(cls, v: str) -> str:
        if v.lower() != 'urgent':
            raise ValueError('Must be urgent')
        return v

class UrgentEvent(WebhookEventBase[UrgentEventPayload]):
    """Only matches events with priority='urgent'"""
    pass
```

### Handler Registration

Multiple ways to register handlers:

```python
bus = EventBus()

# Pattern-based (validation matching)
@bus.on_pattern(GitHubPushEvent)
async def handle_github_push(event: GitHubPushEvent):
    pass

# Activity-based (string matching)
@bus.on_activity("create", "add")  
async def handle_creation(event):
    pass

# Group-based (logical collections)
@bus.on_group("crud")  # Matches create/update/delete group
async def handle_crud(event):
    pass

# Catch-all
@bus.on_any()
async def handle_everything(event):
    pass

# Programmatic registration
bus.register_handler(MyEvent, my_handler)
```

### Activity Groups

Organize activities into logical groups:

```python
bus = EventBus(activity_groups={
    "crud": {"create", "update", "delete"},
    "github": {"push", "pull_request", "issue"},
    "priority": {"urgent", "critical"}
})

@bus.on_group("crud")
async def handle_crud_operations(event):
    print(f"CRUD operation: {event.get_activity()}")
```

### Transform Raw Data

Customize how raw webhook data maps to your payload:

```python
class SlackEventPayload(BaseModel):
    channel: str
    user: str
    text: str

class SlackEvent(WebhookEventBase[SlackEventPayload]):
    @classmethod
    def _transform_raw_data(cls, raw_data: dict) -> dict:
        # Extract from nested Slack structure
        event_data = raw_data.get('event', {})
        return {
            'channel': event_data.get('channel'),
            'user': event_data.get('user'), 
            'text': event_data.get('text')
        }
```

## Integration Patterns

### SmeeMe Integration

WebHooky works seamlessly with SmeeMe for webhook tunneling:

```python
from smeeme import SmeeMe, create_dev_config as smee_config
from webhooky import EventBus, create_dev_config
from webhooky.smeeme import register_with_smeeme

# Setup WebHooky
webhooky_config = create_dev_config()
bus = EventBus()

# Setup SmeeMe
smee_cfg = smee_config(
    url="https://smee.io/your-channel",
    target="http://localhost:8000/webhook",
    enable_queue=True
)
smee = SmeeMe(smee_cfg)

# Connect them
register_with_smeeme(smee, bus, "webhooky_processing")

# Define event patterns in WebHooky
class MemoEvent(WebhookEventBase[MemoPayload]):
    @on_create()
    async def process_memo(self):
        print(f"Memo: {self.payload.name}")

# Start both services
with smee:
    # SmeeMe receives webhooks, WebHooky processes them
    smee.send_test_event({"memo": {"name": "test", "content": "hello"}})
```

### Standalone Server

Run WebHooky as a standalone webhook server:

```python
from webhooky.fastapi import create_app
from webhooky import create_production_config

config = create_production_config(
    timeout_seconds=30.0,
    max_concurrent_handlers=100
)

app = create_app(config=config)

# Deploy with: uvicorn app:app --host 0.0.0.0 --port 8000
```

### Custom FastAPI Integration

Add WebHooky to existing FastAPI app:

```python
from fastapi import FastAPI
from webhooky.fastapi import attach_to_app
from webhooky import EventBus, create_production_config

app = FastAPI()
bus = EventBus()
config = create_production_config()

# Attach WebHooky
integration = attach_to_app(app, bus, config, add_routes=True)

# Your existing routes
@app.get("/")
async def root():
    return {"message": "My API with WebHooky"}
```

## Plugin Development

Create plugins by defining event classes and registering via entry points:

### Plugin Structure

```python
# my_plugin/events.py
from pydantic import BaseModel
from webhooky import WebhookEventBase, on_update

class MyEventPayload(BaseModel):
    plugin_type: str
    data: dict

class MyEvent(WebhookEventBase[MyEventPayload]):
    @on_update()
    async def handle_update(self):
        print(f"Plugin event: {self.payload.plugin_type}")

# Optional plugin initialization
def init_plugin():
    print("My plugin loaded!")

def cleanup_plugin():
    print("My plugin cleaned up!")
```

### Plugin Registration

**pyproject.toml**
```toml
[project.entry-points."webhooky.plugins"]
myplugin = "my_plugin.events"
```

### Plugin Loading

```python
from webhooky import plugin_manager

# Load specific plugin
plugin_manager.load_plugin("myplugin")

# Load all discovered plugins
discovered = plugin_manager.discover_plugins()
for plugin_name in discovered:
    plugin_manager.load_plugin(plugin_name)

# Register with bus
plugin_manager.register_with_bus(bus)
```

## Configuration

### Environment Variables

Configure via environment variables with `WEBHOOKY_` prefix:

```bash
export WEBHOOKY_TIMEOUT_SECONDS=30.0
export WEBHOOKY_MAX_CONCURRENT_HANDLERS=100
export WEBHOOKY_LOG_LEVEL=info
export WEBHOOKY_ENABLE_PLUGINS=true
export WEBHOOKY_API_PREFIX=/api/webhooks
```

### Programmatic Configuration

```python
from webhooky import (
    WebHookyConfig, 
    create_dev_config, 
    create_production_config,
    load_config_from_env
)

# Load from environment
config = load_config_from_env()

# Development preset
dev_config = create_dev_config(
    timeout_seconds=10.0,
    enable_plugins=True,
    log_level=LogLevel.DEBUG
)

# Production preset  
prod_config = create_production_config(
    timeout_seconds=30.0,
    max_concurrent_handlers=100,
    metrics_log_path="/var/log/webhooky.jsonl"
)
```

## Advanced Features

### Metrics and Observability

```python
# Get bus metrics
metrics = bus.get_metrics()
print(f"Success rate: {metrics.success_rate:.1%}")
print(f"Avg processing time: {metrics.average_processing_time:.3f}s")

# Get registry information
from webhooky import event_registry
info = event_registry.get_registry_info()
print(f"Registered classes: {len(info.registered_classes)}")
```

### Validation Testing

```python
# Test data against patterns
validation_result = event_registry.validate_raw_data({
    "priority": "urgent",
    "message": "System alert"
})

print(f"Matches: {validation_result['matches']}")
print(f"Errors: {validation_result['errors']}")
```

### Schema Export

```python
# Export schemas for all event classes
schemas = event_registry.export_schema()
for class_name, schema in schemas.items():
    print(f"{class_name}: {schema}")
```

### Error Handling

```python
# Configure error handling
bus = EventBus(
    timeout_seconds=30.0,
    swallow_exceptions=True,  # Don't crash on handler errors
    max_concurrent_handlers=50
)

# Handle processing results
result = await bus.dispatch_raw(webhook_data)
if not result.success:
    print(f"Processing errors: {result.errors}")
    print(f"Failed handlers: {result.failed_handlers}")
```

## API Reference

### EventBus Methods

- `dispatch_raw(raw_data, headers, source_info)` – Main dispatch method
- `on_pattern(*classes)` – Register pattern-based handler
- `on_activity(*activities)` – Register activity-based handler
- `on_group(*groups)` – Register group-based handler
- `on_any()` – Register catch-all handler
- `get_metrics()` – Get processing metrics
- `reset_metrics()` – Reset metrics counters

### WebhookEventBase Methods

- `matches(raw_data, headers)` – Check if data matches pattern (class method)
- `from_raw(raw_data, headers, source_info)` – Create event from raw data (class method)
- `get_activity()` – Extract activity string for routing
- `process_triggers()` – Execute trigger methods

### Registry Functions

- `event_registry.get_registry_info()` – Get registry state
- `event_registry.validate_raw_data(data)` – Test pattern matching
- `event_registry.export_schema()` – Export all schemas

## Requirements

- Python ≥ 3.11
- Pydantic ≥ 2.7

### Optional Dependencies

- `fastapi` – FastAPI integration and server functionality  
- `typer` + `rich` – CLI tools
- `smeeme` – SmeeMe integration adapter

## Examples

See `examples.py` for comprehensive usage examples including:
- Basic pattern matching
- Activity-based routing  
- Plugin system usage
- Error handling patterns
- SmeeMe integration

## Testing

```bash
# Run tests
pytest tests/

# Test with CLI
webhooky test --json '{"type": "test", "message": "hello"}'

# Validate payload
webhooky validate test-payload.json

# Check system status  
webhooky status --format table
```

## License

MIT License - see LICENSE file for details.