"""Unit and property tests for the CLOSCALL_ settings loader."""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from closcall.config import Settings, load_settings

_VALID_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_closcall_env(monkeypatch)
    settings = load_settings()
    assert settings.environment == "dev"
    assert settings.logging.level == "INFO"


def test_env_prefix_override(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_closcall_env(monkeypatch)
    monkeypatch.setenv("CLOSCALL_ENVIRONMENT", "test")
    assert load_settings().environment == "test"


def test_nested_delimiter(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_closcall_env(monkeypatch)
    monkeypatch.setenv("CLOSCALL_LOGGING__LEVEL", "DEBUG")
    assert load_settings().logging.level == "DEBUG"


def test_unprefixed_env_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_closcall_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "test")
    assert load_settings().environment == "dev"


def test_unknown_prefixed_var_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_closcall_env(monkeypatch)
    monkeypatch.setenv("CLOSCALL_BOGUS", "1")
    with pytest.raises(ValueError, match="CLOSCALL_BOGUS"):
        load_settings()


def test_unknown_nested_var_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_closcall_env(monkeypatch)
    monkeypatch.setenv("CLOSCALL_LOGGING__BOGUS", "1")
    with pytest.raises(ValidationError):
        load_settings()


def test_invalid_environment_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_closcall_env(monkeypatch)
    monkeypatch.setenv("CLOSCALL_ENVIRONMENT", "prod")  # not a core environment
    with pytest.raises(ValidationError):
        load_settings()


@given(level=st.sampled_from(_VALID_LEVELS))
def test_every_valid_level_accepted(level: str) -> None:
    settings = Settings(logging={"level": level})  # type: ignore[arg-type]
    assert settings.logging.level == level


@given(level=st.text(max_size=20).filter(lambda s: s not in _VALID_LEVELS))
def test_every_invalid_level_rejected(level: str) -> None:
    with pytest.raises(ValidationError):
        Settings(logging={"level": level})  # type: ignore[arg-type]


def _clear_closcall_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for key in list(os.environ):
        if key.startswith("CLOSCALL_"):
            monkeypatch.delenv(key)
