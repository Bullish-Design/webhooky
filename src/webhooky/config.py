"""Configuration management for WebHooky."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar

from .models import WebHookyConfig, LogLevel
from .exceptions import WebHookyConfigError

T = TypeVar("T", bound=WebHookyConfig)


def _as_bool(value: str | bool | None, default: bool) -> bool:
    """Convert string/bool/None to boolean."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | int | None, default: int) -> int:
    """Convert string/int/None to integer."""
    if isinstance(value, int):
        return value
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except ValueError:
        return default


def _as_float(value: str | float | None, default: float) -> float:
    """Convert string/float/None to float."""
    if isinstance(value, float):
        return value
    if value is None:
        return default
    try:
        return float(str(value).strip())
    except ValueError:
        return default


def _as_path(value: str | None) -> Optional[Path]:
    """Convert string to Path if not None."""
    if value is None:
        return None
    return Path(str(value).strip())


def _as_list(value: str | None, separator: str = ",") -> List[str]:
    """Convert comma-separated string to list."""
    if not value:
        return []
    return [item.strip() for item in str(value).split(separator) if item.strip()]


class ConfigLoader:
    """Configuration loader with environment variable support."""

    def __init__(self, prefix: str = "WEBHOOKY"):
        self.prefix = prefix

    def load_from_env(
        self,
        config_class: Type[T] = WebHookyConfig,
        env_dict: Optional[Dict[str, str]] = None,
        defaults: Optional[Dict[str, Any]] = None,
    ) -> T:
        """Load configuration from environment variables."""
        env = {**os.environ, **(env_dict or {})}
        config_data = defaults.copy() if defaults else {}

        """
        print(f"\n\n========================== Environment ===============================\n\n")

        print(f"\n\n\n{env}\n\n\n")

        print(f"\n\n ============================== Defaults ==============================\n\n")
        for k, v in env.items():
            # if k.startswith(self.prefix):
            print(f"    {k}={v}")
            """

        # Map environment variables to config fields
        mappings = {
            f"{self.prefix}_TIMEOUT_SECONDS": "timeout_seconds",
            f"{self.prefix}_MAX_CONCURRENT_HANDLERS": "max_concurrent_handlers",
            f"{self.prefix}_SWALLOW_EXCEPTIONS": "swallow_exceptions",
            f"{self.prefix}_LOG_LEVEL": "log_level",
            f"{self.prefix}_ENABLE_METRICS": "enable_metrics",
            f"{self.prefix}_METRICS_LOG_PATH": "metrics_log_path",
            f"{self.prefix}_ENABLE_PLUGINS": "enable_plugins",
            f"{self.prefix}_PLUGIN_PATHS": "plugin_paths",
            f"{self.prefix}_CREATE_FASTAPI_ROUTES": "create_fastapi_routes",
            f"{self.prefix}_API_PREFIX": "api_prefix",
        }

        for env_key, config_key in mappings.items():
            if env_key in env and env[env_key]:
                config_data[config_key] = self._convert_value(config_key, env[env_key])

        # Handle activity groups (JSON format)
        activity_groups_key = f"{self.prefix}_ACTIVITY_GROUPS"
        if activity_groups_key in env and env[activity_groups_key]:
            try:
                import json

                config_data["activity_groups"] = json.loads(env[activity_groups_key])
            except json.JSONDecodeError as e:
                raise WebHookyConfigError(f"Invalid JSON in {activity_groups_key}: {e}")

        try:
            return config_class(**config_data)
        except Exception as e:
            raise WebHookyConfigError(f"Invalid configuration: {e}")

    def _convert_value(self, key: str, value: str) -> Any:
        """Convert string value to appropriate type based on field."""
        conversions = {
            "timeout_seconds": lambda v: _as_float(v, 30.0),
            "max_concurrent_handlers": lambda v: _as_int(v, 50),
            "swallow_exceptions": lambda v: _as_bool(v, True),
            "enable_metrics": lambda v: _as_bool(v, True),
            "enable_plugins": lambda v: _as_bool(v, True),
            "create_fastapi_routes": lambda v: _as_bool(v, True),
            "metrics_log_path": lambda v: _as_path(v),
            "plugin_paths": lambda v: [Path(p) for p in _as_list(v)],
            "log_level": lambda v: LogLevel(v.lower()),
        }

        converter = conversions.get(key)
        if converter:
            try:
                return converter(value)
            except (ValueError, TypeError) as e:
                raise WebHookyConfigError(f"Invalid value for {key}: {value} ({e})")

        return value


class ConfigValidator:
    """Configuration validator with comprehensive checks."""

    @staticmethod
    def validate_config(config: WebHookyConfig) -> None:
        """Validate configuration for common issues."""
        errors = []

        # Timeout validation
        if config.timeout_seconds <= 0:
            errors.append("Timeout must be positive")
        if config.timeout_seconds > 300:
            errors.append("Timeout should not exceed 5 minutes")

        # Concurrency validation
        if config.max_concurrent_handlers < 1:
            errors.append("Max concurrent handlers must be at least 1")
        if config.max_concurrent_handlers > 1000:
            errors.append("Max concurrent handlers should not exceed 1000")

        # Path validation
        if config.metrics_log_path and not config.metrics_log_path.parent.exists():
            errors.append(f"Metrics log directory does not exist: {config.metrics_log_path.parent}")

        for plugin_path in config.plugin_paths:
            if not plugin_path.exists():
                errors.append(f"Plugin path does not exist: {plugin_path}")

        # API prefix validation
        if not config.api_prefix.startswith("/"):
            errors.append("API prefix must start with '/'")

        if errors:
            raise WebHookyConfigError(f"Configuration validation failed: {'; '.join(errors)}")

    @staticmethod
    def check_runtime_requirements(config: WebHookyConfig) -> List[str]:
        """Check runtime requirements and return warnings."""
        warnings = []

        # Check metrics logging
        if config.metrics_log_path:
            try:
                config.metrics_log_path.touch()
            except PermissionError:
                warnings.append(f"No write permission for metrics log: {config.metrics_log_path}")
            except Exception as e:
                warnings.append(f"Cannot access metrics log path: {e}")

        # Check high concurrency
        if config.max_concurrent_handlers > 100:
            warnings.append(f"High concurrency ({config.max_concurrent_handlers}) may consume significant resources")

        # Check plugin paths accessibility
        for plugin_path in config.plugin_paths:
            try:
                list(plugin_path.glob("*.py"))
            except PermissionError:
                warnings.append(f"No read permission for plugin path: {plugin_path}")

        return warnings


# Convenience functions
def load_config_from_env(
    prefix: str = "WEBHOOKY",
    defaults: Optional[Dict[str, Any]] = None,
    validate: bool = True,
) -> WebHookyConfig:
    """Load and optionally validate configuration from environment."""
    loader = ConfigLoader(prefix)
    config = loader.load_from_env(WebHookyConfig, defaults=defaults)

    if validate:
        ConfigValidator.validate_config(config)

    return config


def create_dev_config(
    timeout_seconds: float = 10.0,
    max_concurrent_handlers: int = 20,
    enable_plugins: bool = True,
    log_level: LogLevel = LogLevel.DEBUG,
    **kwargs,
) -> WebHookyConfig:
    """Create a development configuration."""
    return WebHookyConfig(
        timeout_seconds=timeout_seconds,
        max_concurrent_handlers=max_concurrent_handlers,
        swallow_exceptions=False,  # Don't swallow in dev
        log_level=log_level,
        enable_metrics=True,
        enable_plugins=enable_plugins,
        create_fastapi_routes=True,
        **kwargs,
    )


def create_production_config(
    timeout_seconds: float = 30.0,
    max_concurrent_handlers: int = 100,
    enable_plugins: bool = True,
    log_level: LogLevel = LogLevel.INFO,
    metrics_log_path: Optional[str] = None,
    **kwargs,
) -> WebHookyConfig:
    """Create a production configuration."""
    log_path = Path(metrics_log_path) if metrics_log_path else None

    return WebHookyConfig(
        timeout_seconds=timeout_seconds,
        max_concurrent_handlers=max_concurrent_handlers,
        swallow_exceptions=True,  # Swallow in production
        log_level=log_level,
        enable_metrics=True,
        metrics_log_path=log_path,
        enable_plugins=enable_plugins,
        create_fastapi_routes=True,
        **kwargs,
    )


def create_minimal_config(**kwargs) -> WebHookyConfig:
    """Create a minimal configuration with basic settings."""
    return WebHookyConfig(
        timeout_seconds=5.0,
        max_concurrent_handlers=10,
        swallow_exceptions=True,
        log_level=LogLevel.WARNING,
        enable_metrics=False,
        enable_plugins=False,
        create_fastapi_routes=False,
        **kwargs,
    )

