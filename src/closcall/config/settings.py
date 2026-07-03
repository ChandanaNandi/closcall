"""Typed application settings (Bible §6 naming standards).

Environment variables use the ``CLOSCALL_`` prefix; nested settings use ``__``
as the delimiter, e.g. ``CLOSCALL_LOGGING__LEVEL=DEBUG``. Unknown ``CLOSCALL_``
variables are rejected rather than silently ignored.
"""

import os
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_PREFIX = "CLOSCALL_"

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

Environment = Literal["dev", "test"]


class LoggingSettings(BaseModel):
    """Structured-logging configuration."""

    model_config = {"extra": "forbid"}

    level: LogLevel = "INFO"


class Settings(BaseSettings):
    """Root settings aggregate, loaded from the process environment."""

    model_config = SettingsConfigDict(
        env_prefix="CLOSCALL_",
        env_nested_delimiter="__",
        extra="forbid",
    )

    environment: Environment = "dev"
    logging: LoggingSettings = Field(default_factory=LoggingSettings)


def load_settings() -> Settings:
    """Load settings from the environment; raises on invalid or unknown values.

    pydantic-settings silently ignores prefixed variables that match no
    top-level field (observed with pydantic-settings 2.x), so unknown-variable
    rejection is enforced explicitly here: a typo'd variable that silently does
    nothing is a misconfiguration hazard, not a convenience.
    """
    known = {name.upper() for name in Settings.model_fields}
    unknown = sorted(
        key
        for key in os.environ
        if key.startswith(_ENV_PREFIX)
        and key.removeprefix(_ENV_PREFIX).split("__", 1)[0] not in known
    )
    if unknown:
        raise ValueError(f"unknown environment variables: {', '.join(unknown)}")
    return Settings()
