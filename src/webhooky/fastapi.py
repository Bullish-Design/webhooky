"""FastAPI integration for WebHooky."""
from __future__ import annotations

import logging
from typing import Any, Dict

try:
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import JSONResponse
except ImportError as e:
    raise ImportError("FastAPI not installed. Install with: uv add webhooky[fastapi]") from e

from .bus import EventBus
from .models import WebHookyConfig, WebHookyStatus
from .exceptions import WebHookyError

logger = logging.getLogger(__name__)


class WebHookyFastAPI:
    """FastAPI integration for WebHooky webhook processing."""

    def __init__(self, bus: EventBus, config: WebHookyConfig):
        self.bus = bus
        self.config = config

    def add_webhook_routes(self, app: FastAPI, path: str = None) -> None:
        """Add webhook processing endpoint."""
        webhook_path = path or f"{self.config.api_prefix}/webhook"

        @app.post(webhook_path)
        async def process_webhook(request: Request) -> JSONResponse:
            """Process incoming webhook."""
            try:
                # Get request data
                headers = dict(request.headers)
                
                # Try JSON first, fallback to form data
                try:
                    raw_data = await request.json()
                except Exception:
                    form_data = await request.form()
                    raw_data = dict(form_data)

                # Add source info
                source_info = {
                    "client_ip": getattr(request.client, "host", None),
                    "user_agent": headers.get("user-agent"),
                    "method": request.method,
                    "url": str(request.url),
                }

                # Process through bus
                result = await self.bus.process_webhook(raw_data, headers, source_info)

                return JSONResponse(
                    content={
                        "status": "processed",
                        "success": result.success,
                        "matched_patterns": result.matched_patterns,
                        "trigger_count": result.trigger_count,
                        "processing_time": result.processing_time,
                        "errors": result.errors if not result.success else None,
                    },
                    status_code=200 if result.success else 422,
                )

            except Exception as e:
                logger.error(f"Webhook processing failed: {e}")
                raise HTTPException(status_code=500, detail=f"Processing failed: {e}")

    def add_status_routes(self, app: FastAPI, prefix: str = None) -> None:
        """Add WebHooky status and management routes."""
        status_prefix = prefix or f"{self.config.api_prefix}/status"

        @app.get(status_prefix)
        async def get_status() -> WebHookyStatus:
            """Get WebHooky system status."""
            bus_stats = self.bus.get_stats()
            
            return WebHookyStatus(
                running=True,
                registered_classes=self.bus.get_registered_classes(),
                class_count=len(self.bus.get_registered_classes()),
                total_processed=bus_stats['total_processed'],
                total_matches=bus_stats['total_matches'],
                total_triggers=bus_stats['total_triggers'],
                total_errors=bus_stats['total_errors'],
            )

        @app.get(f"{status_prefix}/registered")
        async def get_registered_classes() -> Dict[str, Any]:
            """Get registered event classes."""
            return {
                "classes": self.bus.get_registered_classes(),
                "count": len(self.bus.get_registered_classes()),
            }

        @app.post(f"{status_prefix}/reset")
        async def reset_stats() -> Dict[str, str]:
            """Reset bus statistics."""
            self.bus.reset_stats()
            return {"status": "statistics reset"}

    def add_test_routes(self, app: FastAPI, prefix: str = None) -> None:
        """Add testing and debugging routes."""
        test_prefix = prefix or f"{self.config.api_prefix}/test"

        @app.post(f"{test_prefix}/webhook")
        async def test_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
            """Test webhook processing with custom payload."""
            try:
                result = await self.bus.process_webhook(payload)
                return {
                    "test_result": "success" if result.success else "failed",
                    "processing_result": result.model_dump(),
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))


def create_app(
    bus: EventBus, 
    config: WebHookyConfig = None,
    add_routes: bool = True,
    **fastapi_kwargs
) -> FastAPI:
    """Create FastAPI app with WebHooky integration."""
    
    if config is None:
        from .config import create_config
        config = create_config()

    app_kwargs = {
        "title": "WebHooky Webhook Processor",
        "description": "Simple Pydantic-based webhook event processing",
        "version": "0.3.0",
        **fastapi_kwargs,
    }

    app = FastAPI(**app_kwargs)
    integration = WebHookyFastAPI(bus, config)

    if add_routes:
        integration.add_webhook_routes(app)
        integration.add_status_routes(app)
        integration.add_test_routes(app)

    @app.get("/health")
    async def health_check() -> Dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy", "service": "webhooky"}

    return app
