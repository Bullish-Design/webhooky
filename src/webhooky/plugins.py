"""Plugin system for WebHooky extensibility."""

from __future__ import annotations

import asyncio
import importlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

try:
    from importlib.metadata import entry_points, PackageNotFoundError
except ImportError:
    from importlib_metadata import entry_points, PackageNotFoundError

from .models import PluginInfo
from .events import WebhookEventBase

logger = logging.getLogger(__name__)


class PluginManager:
    """
    Plugin manager for WebHooky extensions.
    
    Supports both entry point discovery and direct module loading.
    """

    def __init__(self):
        self._loaded_plugins: Dict[str, Any] = {}
        self._plugin_info: Dict[str, PluginInfo] = {}
        self._event_classes: Dict[str, List[Type[WebhookEventBase]]] = {}
        self._handlers: Dict[str, List[Any]] = {}

    def discover_plugins(self, group_name: str = "webhooky.plugins") -> List[str]:
        """Discover plugins via entry points."""
        discovered = []
        
        try:
            eps = entry_points()
            if hasattr(eps, 'select'):
                # Python 3.10+
                group = eps.select(group=group_name)
            else:
                # Python 3.9 compatibility
                group = [ep for ep in eps if getattr(ep, 'group', None) == group_name]
            
            for entry_point in group:
                discovered.append(entry_point.name)
                logger.debug(f"Discovered plugin: {entry_point.name}")
                
        except Exception as e:
            logger.warning(f"Plugin discovery failed: {e}")
        
        return discovered

    def load_plugin(self, plugin_name: str, group_name: str = "webhooky.plugins") -> bool:
        """Load a specific plugin by name from entry points."""
        if plugin_name in self._loaded_plugins:
            logger.debug(f"Plugin already loaded: {plugin_name}")
            return True

        try:
            # Find entry point
            eps = entry_points()
            if hasattr(eps, 'select'):
                group = eps.select(group=group_name)
            else:
                group = [ep for ep in eps if getattr(ep, 'group', None) == group_name]
            
            plugin_entry = None
            for ep in group:
                if ep.name == plugin_name:
                    plugin_entry = ep
                    break
            
            if not plugin_entry:
                self._plugin_info[plugin_name] = PluginInfo(
                    name=plugin_name,
                    loaded=False,
                    load_error="Entry point not found"
                )
                return False

            # Load the plugin module
            plugin_module = plugin_entry.load()
            return self._initialize_plugin(plugin_name, plugin_module)

        except Exception as e:
            error_msg = f"Failed to load plugin {plugin_name}: {e}"
            logger.error(error_msg)
            self._plugin_info[plugin_name] = PluginInfo(
                name=plugin_name,
                loaded=False,
                load_error=str(e)
            )
            return False

    def load_module_plugin(self, module_name: str, plugin_alias: str = None) -> bool:
        """Load plugin directly from module name."""
        alias = plugin_alias or module_name.split('.')[-1]
        
        if alias in self._loaded_plugins:
            logger.debug(f"Module plugin already loaded: {alias}")
            return True

        try:
            plugin_module = importlib.import_module(module_name)
            return self._initialize_plugin(alias, plugin_module)
        except Exception as e:
            error_msg = f"Failed to load module plugin {module_name}: {e}"
            logger.error(error_msg)
            self._plugin_info[alias] = PluginInfo(
                name=alias,
                loaded=False,
                load_error=str(e)
            )
            return False

    def load_directory_plugins(self, plugin_dir: Path) -> Dict[str, bool]:
        """Load all plugins from a directory."""
        results = {}
        
        if not plugin_dir.exists() or not plugin_dir.is_dir():
            logger.warning(f"Plugin directory not found: {plugin_dir}")
            return results

        for plugin_file in plugin_dir.glob("*.py"):
            if plugin_file.stem.startswith("_"):
                continue  # Skip private files
                
            plugin_name = plugin_file.stem
            try:
                spec = importlib.util.spec_from_file_location(plugin_name, plugin_file)
                if spec and spec.loader:
                    plugin_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(plugin_module)
                    results[plugin_name] = self._initialize_plugin(plugin_name, plugin_module)
                else:
                    results[plugin_name] = False
            except Exception as e:
                logger.error(f"Failed to load plugin from {plugin_file}: {e}")
                results[plugin_name] = False

        return results

    def _initialize_plugin(self, plugin_name: str, plugin_module: Any) -> bool:
        """Initialize a loaded plugin module."""
        try:
            # Create plugin info
            info = PluginInfo(
                name=plugin_name,
                version=getattr(plugin_module, '__version__', None),
                description=getattr(plugin_module, '__doc__', None),
                author=getattr(plugin_module, '__author__', None)
            )

            # Extract event classes
            event_classes = self._extract_event_classes(plugin_module)
            self._event_classes[plugin_name] = event_classes
            info.event_classes = [cls.__name__ for cls in event_classes]

            # Extract handlers
            handlers = self._extract_handlers(plugin_module)
            self._handlers[plugin_name] = handlers
            info.handlers = [getattr(h, '__name__', str(h)) for h in handlers]

            # Extract activity groups
            activity_groups = getattr(plugin_module, 'ACTIVITY_GROUPS', {})
            info.activity_groups = activity_groups

            # Call plugin initialization if available
            if hasattr(plugin_module, 'init_plugin'):
                init_func = plugin_module.init_plugin
                if asyncio.iscoroutinefunction(init_func):
                    # Store for async initialization later
                    info.load_error = "Async init required"
                else:
                    init_func()

            # Store plugin
            self._loaded_plugins[plugin_name] = plugin_module
            info.loaded = True
            self._plugin_info[plugin_name] = info
            
            logger.info(f"Loaded plugin: {plugin_name} ({len(event_classes)} events, {len(handlers)} handlers)")
            return True

        except Exception as e:
            error_msg = f"Plugin initialization failed: {e}"
            logger.error(f"Plugin {plugin_name} initialization failed: {e}")
            self._plugin_info[plugin_name] = PluginInfo(
                name=plugin_name,
                loaded=False,
                load_error=error_msg
            )
            return False

    def _extract_event_classes(self, plugin_module: Any) -> List[Type[WebhookEventBase]]:
        """Extract WebhookEventBase subclasses from plugin module."""
        event_classes = []
        
        for attr_name in dir(plugin_module):
            if attr_name.startswith('_'):
                continue
                
            attr = getattr(plugin_module, attr_name)
            
            if (isinstance(attr, type) and 
                issubclass(attr, WebhookEventBase) and 
                attr is not WebhookEventBase):
                event_classes.append(attr)

        return event_classes

    def _extract_handlers(self, plugin_module: Any) -> List[Any]:
        """Extract handler functions from plugin module."""
        handlers = []
        
        for attr_name in dir(plugin_module):
            if attr_name.startswith('_'):
                continue
                
            attr = getattr(plugin_module, attr_name)
            
            # Look for functions with handler markers (removed for explicitness)
            #if (callable(attr) and 
            #    (hasattr(attr, '_webhook_handler') or 
            #     attr_name.startswith('handle_') or
            #     attr_name.endswith('_handler'))):
            #    handlers.append(attr)

            if callable(attr) and hasattr(attr, '_webhook_handler'): # [cite: 269]
                handlers.append(attr)

        return handlers

    def register_with_bus(self, bus) -> None:
        """Register all loaded plugin handlers with an event bus."""
        for plugin_name, handlers in self._handlers.items():
            for handler in handlers:
                handler_name = getattr(handler, '__name__', 'unknown_handler')
                # Check for handler metadata
                if hasattr(handler, '_webhook_pattern'):
                    # Pattern-based handler
                    pattern_class = handler._webhook_pattern
                    bus.register_handler(pattern_class, handler) # [cite: 271]
                    logger.debug(f"Registered pattern handler '{handler_name}' from plugin '{plugin_name}'")
                elif hasattr(handler, '_webhook_activity'):
                    # Activity-based handler
                    activity = handler._webhook_activity
                    bus.register_activity_handler(activity, handler) # [cite: 272]
                    logger.debug(f"Registered activity handler '{handler_name}' from plugin '{plugin_name}'")
                else:
                    # Generic handler - register as catch-all with a warning
                    logger.warning(
                        f"Handler '{handler_name}' from plugin '{plugin_name}' was decorated but "
                        f"specified no pattern or activity. Registering as a catch-all ('on_any'). "
                        f"This will run for EVERY event. To be more specific, use "
                        f"@webhook_handler(pattern=YourEvent) or @webhook_handler(activity='your_activity')."
                    )
                    bus.on_any()(handler)
                    
                logger.debug(f"Registered handler {handler_name} from plugin {plugin_name}")

    async def async_init_plugins(self) -> None:
        """Initialize plugins that require async setup."""
        for plugin_name, plugin_module in self._loaded_plugins.items():
            if hasattr(plugin_module, 'init_plugin'):
                init_func = plugin_module.init_plugin
                if asyncio.iscoroutinefunction(init_func):
                    try:
                        await init_func()
                        self._plugin_info[plugin_name].load_error = None
                        logger.info(f"Async initialized plugin: {plugin_name}")
                    except Exception as e:
                        error_msg = f"Async init failed: {e}"
                        self._plugin_info[plugin_name].load_error = error_msg
                        logger.error(f"Plugin {plugin_name} async init failed: {e}")

    def unload_plugin(self, plugin_name: str) -> bool:
        """Unload a plugin and clean up resources."""
        if plugin_name not in self._loaded_plugins:
            return False

        try:
            plugin_module = self._loaded_plugins[plugin_name]
            
            # Call cleanup if available
            if hasattr(plugin_module, 'cleanup_plugin'):
                cleanup_func = plugin_module.cleanup_plugin
                if asyncio.iscoroutinefunction(cleanup_func):
                    logger.warning(f"Plugin {plugin_name} has async cleanup - use unload_plugin_async")
                else:
                    cleanup_func()

            # Remove from tracking
            del self._loaded_plugins[plugin_name]
            self._event_classes.pop(plugin_name, None)
            self._handlers.pop(plugin_name, None)
            
            # Update info
            if plugin_name in self._plugin_info:
                self._plugin_info[plugin_name].loaded = False

            logger.info(f"Unloaded plugin: {plugin_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to unload plugin {plugin_name}: {e}")
            return False

    async def unload_plugin_async(self, plugin_name: str) -> bool:
        """Async version of unload_plugin for plugins with async cleanup."""
        if plugin_name not in self._loaded_plugins:
            return False

        try:
            plugin_module = self._loaded_plugins[plugin_name]
            
            # Call cleanup if available
            if hasattr(plugin_module, 'cleanup_plugin'):
                cleanup_func = plugin_module.cleanup_plugin
                if asyncio.iscoroutinefunction(cleanup_func):
                    await cleanup_func()
                else:
                    cleanup_func()

            # Remove from tracking
            del self._loaded_plugins[plugin_name]
            self._event_classes.pop(plugin_name, None)
            self._handlers.pop(plugin_name, None)
            
            # Update info
            if plugin_name in self._plugin_info:
                self._plugin_info[plugin_name].loaded = False

            logger.info(f"Async unloaded plugin: {plugin_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to async unload plugin {plugin_name}: {e}")
            return False

    def get_plugin_info(self, plugin_name: str) -> Optional[PluginInfo]:
        """Get information about a specific plugin."""
        return self._plugin_info.get(plugin_name)

    def get_all_plugin_info(self) -> Dict[str, PluginInfo]:
        """Get information about all plugins."""
        return self._plugin_info.copy()

    def get_loaded_plugins(self) -> List[str]:
        """Get list of successfully loaded plugin names."""
        return [name for name, info in self._plugin_info.items() if info.loaded]

    def get_plugin_event_classes(self, plugin_name: str) -> List[Type[WebhookEventBase]]:
        """Get event classes provided by a specific plugin."""
        return self._event_classes.get(plugin_name, [])

    def get_all_plugin_event_classes(self) -> List[Type[WebhookEventBase]]:
        """Get all event classes from all loaded plugins."""
        all_classes = []
        for classes in self._event_classes.values():
            all_classes.extend(classes)
        return all_classes

    def reload_plugin(self, plugin_name: str) -> bool:
        """Reload a plugin (unload then load again)."""
        if plugin_name in self._loaded_plugins:
            plugin_module = self._loaded_plugins[plugin_name]
            module_name = getattr(plugin_module, '__name__', plugin_name)
            
            # Unload first
            if not self.unload_plugin(plugin_name):
                return False
                
            # Reload module
            try:
                importlib.reload(plugin_module)
                return self._initialize_plugin(plugin_name, plugin_module)
            except Exception as e:
                logger.error(f"Failed to reload plugin {plugin_name}: {e}")
                return False
        
        return False


# Global plugin manager instance
plugin_manager = PluginManager()


# Decorators for plugin developers
def webhook_handler(pattern_or_activity=None, activity=None):
    """Decorator to mark functions as webhook handlers."""
    def decorator(func):
        if pattern_or_activity and isinstance(pattern_or_activity, type):
            func._webhook_pattern = pattern_or_activity
        elif pattern_or_activity and isinstance(pattern_or_activity, str):
            func._webhook_activity = pattern_or_activity
        elif activity:
            func._webhook_activity = activity
        else:
            func._webhook_handler = True
        return func
    return decorator
