"""FastAPI adapter for WebHooky webhook processing."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional

try:
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import JSONResponse
except ImportError as e:
    raise ImportError("FastAPI not installed. Install with: uv add webhooky[fastapi]") from e

from .bus import EventBus
from .models import WebHookyConfig, ProcessingResult
from .plugins import plugin_manager
from .registry import event_registry
from .exceptions import AdapterError

logger = logging.getLogger(__name__)


class WebHookyFastAPI:
    """FastAPI integration for WebHooky webhook processing."""

    def __init__(self, bus: EventBus, config: Optional[WebHookyConfig] = None):
        self.bus = bus
        self.config = config or WebHookyConfig()
        self._started = False

    def create_lifespan(self) -> Any:
        """Create FastAPI lifespan context manager."""

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
            # Startup
            logger.info("Starting WebHooky with FastAPI")
            await self._startup()
            app.state.webhooky_bus = self.bus
            app.state.webhooky_config = self.config
            yield
            # Shutdown
            logger.info("Stopping WebHooky with FastAPI")
            await self._shutdown()

        return lifespan

    async def _startup(self) -> None:
        """Startup logic for WebHooky."""
        try:
            # Load plugins if enabled
            if self.config.enable_plugins:
                await self._load_plugins()

            self._started = True
            logger.info("WebHooky started successfully")

        except Exception as e:
            logger.error(f"WebHooky startup failed: {e}")
            raise AdapterError(f"Failed to start WebHooky: {e}")

    async def _shutdown(self) -> None:
        """Shutdown logic for WebHooky."""
        try:
            # Cleanup plugins
            if self.config.enable_plugins:
                await self._cleanup_plugins()

            self._started = False
            logger.info("WebHooky stopped successfully")

        except Exception as e:
            logger.error(f"WebHooky shutdown failed: {e}")

    async def _load_plugins(self) -> None:
        """Load and initialize plugins."""
        try:
            # Discover and load plugins from entry points
            discovered = plugin_manager.discover_plugins()
            for plugin_name in discovered:
                plugin_manager.load_plugin(plugin_name)

            # Load plugins from configured paths
            for plugin_path in self.config.plugin_paths:
                plugin_manager.load_directory_plugins(plugin_path)

            # Async initialize plugins
            await plugin_manager.async_init_plugins()

            # Register plugin handlers with bus
            plugin_manager.register_with_bus(self.bus)

            loaded_count = len(plugin_manager.get_loaded_plugins())
            logger.info(f"Loaded {loaded_count} plugins")

        except Exception as e:
            logger.error(f"Plugin loading failed: {e}")

    async def _cleanup_plugins(self) -> None:
        """Cleanup loaded plugins."""
        try:
            loaded_plugins = plugin_manager.get_loaded_plugins()
            for plugin_name in loaded_plugins:
                await plugin_manager.unload_plugin_async(plugin_name)
        except Exception as e:
            logger.error(f"Plugin cleanup failed: {e}")

    def add_webhook_routes(self, app: FastAPI, path: str = "/webhook") -> None:
        """Add webhook processing endpoint."""

        @app.post(path)
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

                # print(f"\n\nReceived webhook: {raw_data}\n\n")

                # Add source info
                source_info = {
                    "client_ip": getattr(request.client, "host", None),
                    "user_agent": headers.get("user-agent"),
                    "method": request.method,
                    "url": str(request.url),
                }

                # Process through bus
                result = await self.bus.dispatch_raw(raw_data, headers, source_info)

                # Return processing result
                return JSONResponse(
                    content={
                        "status": "processed",
                        "success": result.success,
                        "matched_patterns": result.matched_patterns,
                        "handler_count": result.handler_count,
                        "processing_time": result.processing_time,
                        "errors": result.errors if not result.success else None,
                    },
                    status_code=200 if result.success else 422,
                )

            except Exception as e:
                logger.error(f"Webhook processing failed: {e}")
                raise HTTPException(status_code=500, detail=f"Processing failed: {e}")

    def add_status_routes(self, app: FastAPI, prefix: str = "/status") -> None:
        """Add WebHooky status and management routes."""

        @app.get(f"{prefix}")
        async def get_status() -> Dict[str, Any]:
            """Get WebHooky system status."""
            metrics = self.bus.get_metrics()
            registry_info = event_registry.get_registry_info()

            return {
                "started": self._started,
                "bus_metrics": metrics.model_dump(),
                "registry": registry_info.model_dump(),
                "handler_counts": self.bus.get_handler_count(),
                "registered_patterns": self.bus.get_registered_patterns(),
                "registered_activities": self.bus.get_registered_activities(),
            }

        @app.get(f"{prefix}/metrics")
        async def get_metrics() -> Dict[str, Any]:
            """Get detailed metrics."""
            return self.bus.get_metrics().model_dump()

        @app.get(f"{prefix}/registry")
        async def get_registry_info() -> Dict[str, Any]:
            """Get event registry information."""
            return event_registry.get_registry_info().model_dump()

        @app.get(f"{prefix}/plugins")
        async def get_plugin_info() -> Dict[str, Any]:
            """Get plugin information."""
            if not self.config.enable_plugins:
                return {"enabled": False}

            return {
                "enabled": True,
                "loaded_plugins": plugin_manager.get_loaded_plugins(),
                "plugin_info": {name: info.model_dump() for name, info in plugin_manager.get_all_plugin_info().items()},
            }

        @app.post(f"{prefix}/reset-metrics")
        async def reset_metrics() -> Dict[str, str]:
            """Reset bus metrics."""
            self.bus.reset_metrics()
            event_registry.reset_stats()
            return {"status": "metrics reset"}

    def add_test_routes(self, app: FastAPI, prefix: str = "/test") -> None:
        """Add testing and debugging routes."""

        @app.post(f"{prefix}/webhook")
        async def test_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
            """Test webhook processing with custom payload."""
            try:
                result = await self.bus.dispatch_raw(payload)
                return {
                    "test_result": "success" if result.success else "failed",
                    "processing_result": {
                        "matched_patterns": result.matched_patterns,
                        "handler_count": result.handler_count,
                        "processing_time": result.processing_time,
                        "errors": result.errors,
                    },
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @app.post(f"{prefix}/validate")
        async def validate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
            """Validate payload against all registered patterns."""
            return event_registry.validate_raw_data(payload)

        @app.get(f"{prefix}/schema")
        async def get_event_schemas() -> Dict[str, Any]:
            """Get schemas for all registered event classes."""
            return event_registry.export_schema()


def create_app(bus: Optional[EventBus] = None, config: Optional[WebHookyConfig] = None, **fastapi_kwargs) -> FastAPI:
    """Create FastAPI app with WebHooky integration."""

    # Create default bus and config if not provided
    if not bus:
        from ..config import create_dev_config

        config = config or create_dev_config()
        bus = EventBus(
            timeout_seconds=config.timeout_seconds,
            max_concurrent_handlers=config.max_concurrent_handlers,
            swallow_exceptions=config.swallow_exceptions,
            enable_metrics=config.enable_metrics,
            activity_groups={k: set(v) for k, v in config.activity_groups.items()},
        )

    config = config or WebHookyConfig()

    # Create FastAPI app
    app_kwargs = {
        "title": "WebHooky Webhook Processor",
        "description": "Validation-based webhook event processing",
        "version": "0.1.0",
        **fastapi_kwargs,
    }

    integration = WebHookyFastAPI(bus, config)
    app = FastAPI(lifespan=integration.create_lifespan(), **app_kwargs)

    # Add routes if enabled
    if config.create_fastapi_routes:
        integration.add_webhook_routes(app, f"{config.api_prefix}/webhook")
        integration.add_status_routes(app, f"{config.api_prefix}/status")
        integration.add_test_routes(app, f"{config.api_prefix}/test")

    # Add health check
    @app.get("/health")
    async def health_check() -> Dict[str, Any]:
        """Health check endpoint."""
        return {"status": "healthy" if integration._started else "starting", "service": "webhooky", "version": "0.1.0"}

    return app


def attach_to_app(
    app: FastAPI, bus: EventBus, config: Optional[WebHookyConfig] = None, add_routes: bool = True
) -> WebHookyFastAPI:
    """Attach WebHooky to existing FastAPI app."""

    config = config or WebHookyConfig()
    integration = WebHookyFastAPI(bus, config)

    # Set lifespan
    if hasattr(app.router, "lifespan_context"):
        app.router.lifespan_context = integration.create_lifespan()
    else:
        # Legacy event handlers for older FastAPI
        @app.on_event("startup")
        async def startup():
            await integration._startup()

        @app.on_event("shutdown")
        async def shutdown():
            await integration._shutdown()

    # Add routes if requested
    if add_routes:
        integration.add_webhook_routes(app)
        integration.add_status_routes(app)
        integration.add_test_routes(app)

    return integration

