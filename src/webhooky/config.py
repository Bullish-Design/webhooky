"""Configuration management for WebHooky."""
from __future__ import annotations

import os
from typing import Any, Dict

from .models import WebHookyConfig
from .exceptions import WebHookyConfigError


def create_config(
    timeout_seconds: float = 30.0,
    fallback_to_generic: bool = True,
    log_level: str = "INFO",
    enable_fastapi: bool = True,
    api_prefix: str = "/webhooks",
    host: str = "127.0.0.1",
    port: int = 8000,
    **kwargs
) -> WebHookyConfig:
    """Create configuration with specified values."""
    return WebHookyConfig(
        timeout_seconds=timeout_seconds,
        fallback_to_generic=fallback_to_generic,
        log_level=log_level,
        enable_fastapi=enable_fastapi,
        api_prefix=api_prefix,
        host=host,
        port=port,
        **kwargs
    )


def load_config_from_env(prefix: str = "WEBHOOKY") -> WebHookyConfig:
    """Load configuration from environment variables."""
    env_values: Dict[str, Any] = {}
    
    # Map environment variables to config fields
    mappings = {
        f"{prefix}_TIMEOUT_SECONDS": ("timeout_seconds", float),
        f"{prefix}_FALLBACK_TO_GENERIC": ("fallback_to_generic", _as_bool),
        f"{prefix}_LOG_LEVEL": ("log_level", str),
        f"{prefix}_ENABLE_FASTAPI": ("enable_fastapi", _as_bool),
        f"{prefix}_API_PREFIX": ("api_prefix", str),
        f"{prefix}_HOST": ("host", str),
        f"{prefix}_PORT": ("port", int),
    }
    
    for env_key, (config_key, converter) in mappings.items():
        env_value = os.getenv(env_key)
        if env_value:
            try:
                env_values[config_key] = converter(env_value)
            except (ValueError, TypeError) as e:
                raise WebHookyConfigError(f"Invalid value for {env_key}: {env_value} ({e})")
    
    try:
        return WebHookyConfig(**env_values)
    except Exception as e:
        raise WebHookyConfigError(f"Invalid configuration: {e}")


def _as_bool(value: str) -> bool:
    """Convert string to boolean."""
    return value.strip().lower() in {"1", "true", "yes", "on"}


def validate_config(config: WebHookyConfig) -> None:
    """Validate configuration for common issues."""
    errors = []
    
    if config.timeout_seconds <= 0:
        errors.append("timeout_seconds must be positive")
    
    if config.timeout_seconds > 300:
        errors.append("timeout_seconds should not exceed 5 minutes")
    
    if not config.api_prefix.startswith("/"):
        errors.append("api_prefix must start with '/'")
    
    if config.port < 1 or config.port > 65535:
        errors.append("port must be between 1 and 65535")
    
    if errors:
        raise WebHookyConfigError(f"Configuration validation failed: {'; '.join(errors)}")
