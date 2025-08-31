"""SmeeMe integration adapter for WebHooky."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from .bus import EventBus
from .models import ProcessingResult

logger = logging.getLogger(__name__)


class SmeeEventAdapter:
    """
    Adapter to process SmeeMe events through WebHooky.

    Provides clean integration between SmeeMe's workflow system
    and WebHooky's validation-based event processing.
    """

    def __init__(self, bus: EventBus, extract_payload: bool = True):
        self.bus = bus
        self.extract_payload = extract_payload

    def create_workflow_handler(self):
        """Create a workflow handler for SmeeMe registration."""

        def handle_smee_event(job):
            """Synchronous wrapper for SmeeMe workflow system."""
            try:
                # Extract event data from SmeeMe WorkflowJob
                smee_event = job.event
                raw_data = self._extract_webhook_data(smee_event)
                headers = smee_event.headers
                source_info = self._extract_source_info(smee_event)

                # Process through WebHooky bus
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(self.bus.dispatch_raw(raw_data, headers, source_info))

                    logger.info(f"Processed SmeeMe event: {result.matched_patterns}")
                    return result.model_dump()

                finally:
                    loop.close()

            except Exception as e:
                logger.error(f"SmeeMe event processing failed: {e}")
                raise

        return handle_smee_event

    async def process_smee_event_async(self, smee_event) -> ProcessingResult:
        """
        Async processing of SmeeMe events.

        For use in async contexts or when directly integrating with SmeeMe.
        """
        raw_data = self._extract_webhook_data(smee_event)
        headers = smee_event.headers
        source_info = self._extract_source_info(smee_event)

        return await self.bus.dispatch_raw(raw_data, headers, source_info)

    def _extract_webhook_data(self, smee_event) -> Dict[str, Any]:
        """Extract webhook data from SmeeEvent."""
        try:
            # Get JSON body if available
            if hasattr(smee_event, "get_json_body"):
                json_body = smee_event.get_json_body()
                if json_body:
                    return json_body

            # Fallback to raw body
            if hasattr(smee_event, "body"):
                body = smee_event.body
                if isinstance(body, dict):
                    return body
                elif isinstance(body, str):
                    try:
                        import json

                        return json.loads(body)
                    except json.JSONDecodeError:
                        # Return as text payload
                        return {"text": body}

            return {}

        except Exception as e:
            logger.warning(f"Failed to extract webhook data: {e}")
            return {}

    def _extract_source_info(self, smee_event) -> Dict[str, Any]:
        """Extract source information from SmeeEvent."""
        source_info = {}

        # Standard SmeeEvent fields
        if hasattr(smee_event, "source_ip"):
            source_info["source_ip"] = smee_event.source_ip
        if hasattr(smee_event, "receiver_port"):
            source_info["receiver_port"] = smee_event.receiver_port
        if hasattr(smee_event, "timestamp"):
            source_info["smee_timestamp"] = smee_event.timestamp
        if hasattr(smee_event, "forwarded"):
            source_info["was_forwarded"] = smee_event.forwarded
        if hasattr(smee_event, "error"):
            source_info["smee_error"] = smee_event.error

        source_info["source"] = "smeeme"
        return source_info


def register_with_smeeme(smee_instance, bus: EventBus, workflow_type: str = "webhooky") -> None:
    """
    Register WebHooky bus with SmeeMe instance.

    Args:
        smee_instance: SmeeMe instance
        bus: WebHooky EventBus
        workflow_type: Workflow type name for SmeeMe registration
    """
    adapter = SmeeEventAdapter(bus)
    handler = adapter.create_workflow_handler()

    # Register with SmeeMe's workflow system
    smee_instance.register_workflow(workflow_type, handler)
    logger.info(f"Registered WebHooky bus with SmeeMe as workflow type: {workflow_type}")


def create_smeeme_forwarder(bus: EventBus) -> Any:
    """
    Create a simple event handler that forwards to SmeeMe.

    For cases where you want WebHooky to process events and forward to SmeeMe.
    """

    def forward_to_smeeme(event) -> None:
        """Forward WebHooky event to SmeeMe for tunneling."""
        try:
            # This would require SmeeMe to accept direct events
            # Implementation depends on SmeeMe's API
            logger.info(f"Forwarding {event.__class__.__name__} to SmeeMe")

        except Exception as e:
            logger.error(f"Failed to forward to SmeeMe: {e}")

    return forward_to_smeeme


# Example integration patterns
class SmeeIntegrationExample:
    """Example integration patterns with SmeeMe."""

    @staticmethod
    def basic_integration():
        """Basic integration example."""
        # This would be in user code
        from webhooky import EventBus, create_dev_config, create_bus
        # from smeeme import SmeeMe, create_dev_config as smee_dev_config

        # Setup WebHooky
        config = create_dev_config()
        bus = create_bus(config)

        # Setup SmeeMe (commented to avoid import dependency)
        # smee_config = smee_dev_config(
        #     url="https://smee.io/your-channel",
        #     target="http://localhost:8000/webhook",
        #     enable_queue=True
        # )
        # smee = SmeeMe(smee_config)

        # Connect them
        # register_with_smeeme(smee, bus, "webhooky_processing")

        # Define webhook events in WebHooky
        from pydantic import BaseModel
        from webhooky import WebhookEventBase, on_create

        class MemoPayload(BaseModel):
            name: str
            content: str

        class MemoEvent(WebhookEventBase[MemoPayload]):
            @on_create()
            async def process_memo(self):
                print(f"Processing memo: {self.payload.name}")

        # Start both services
        # with smee:
        #     # SmeeMe receives webhooks, forwards to WebHooky via workflow queue
        #     smee.send_test_event({"name": "test", "content": "hello world"})

        return bus

    @staticmethod
    def fastapi_integration():
        """FastAPI integration example."""
        from webhooky.fastapi import create_app
        from webhooky import create_dev_config

        # Create WebHooky FastAPI app
        config = create_dev_config()
        app = create_app(config=config)

        # SmeeMe would be configured to forward to this app
        # smee_config = smee_dev_config(
        #     url="https://smee.io/your-channel",
        #     target="http://localhost:8000/webhooks/webhook"  # WebHooky endpoint
        # )

        return app

