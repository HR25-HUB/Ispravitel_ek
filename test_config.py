import importlib
import os
import types

import pytest

import config as config_module


def reload_config(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> types.ModuleType:
    # Clear env and set provided
    for k in list(os.environ.keys()):
        if k in env or k in {
            "USE_MOCKS", "MOCK_PROFILE", "SEED", "STREAMLIT_PORT", "LOG_LEVEL",
            "CATALOG_API_URL", "CATALOG_API_KEY", "CATALOG_ID",
            "COZE_API_URL", "COZE_API_KEY", "CONFIDENCE_THRESHOLD",
            "CATALOG_TIMEOUT_SEC", "CATALOG_RETRIES",
            "CATALOG_BACKOFF_BASE_MS", "CATALOG_BACKOFF_MAX_MS", "CATALOG_BACKOFF_JITTER_MS",
            "BACKOFF_BASE_MS", "BACKOFF_MAX_MS", "BACKOFF_JITTER_MS",
        }:
            monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    # Reload module to re-read env
    return importlib.reload(config_module)


def test_defaults_with_mocks(monkeypatch: pytest.MonkeyPatch):
    mod = reload_config(monkeypatch, {
        "USE_MOCKS": "true",
        "MOCK_PROFILE": "happy",
        "SEED": "42",
        "LOG_LEVEL": "INFO",
    })
    cfg = mod.load_config()
    assert cfg.use_mocks is True
    assert cfg.mock_profile == "happy"
    assert cfg.seed == 42
    assert cfg.streamlit_port == 8501
    assert cfg.log_level == "INFO"
    assert 0.0 <= cfg.confidence_threshold <= 1.0
    assert cfg.confidence_threshold == 0.7  # default
    assert cfg.catalog_timeout_sec == 10.0
    assert cfg.catalog_retries == 3
    assert cfg.catalog_backoff_base_ms == 100
    assert cfg.catalog_backoff_max_ms == 2000
    assert cfg.catalog_backoff_jitter_ms == 100
    assert cfg.backoff_base_ms == 100
    assert cfg.backoff_max_ms == 2000
    assert cfg.backoff_jitter_ms == 100
    # Catalog fields may be None in mock mode
    assert cfg.catalog_api_url is None


def test_invalid_mock_profile(monkeypatch: pytest.MonkeyPatch):
    mod = reload_config(monkeypatch, {
        "USE_MOCKS": "true",
        "MOCK_PROFILE": "unknown",
    })
    with pytest.raises(ValueError):
        mod.load_config()


def test_confidence_threshold_parsing_and_bounds(monkeypatch: pytest.MonkeyPatch):
    # valid value
    mod = reload_config(monkeypatch, {
        "USE_MOCKS": "true",
        "MOCK_PROFILE": "happy",
        "CONFIDENCE_THRESHOLD": "0.85",
    })
    cfg = mod.load_config()
    assert cfg.confidence_threshold == 0.85

    # invalid format
    mod = reload_config(monkeypatch, {
        "USE_MOCKS": "true",
        "MOCK_PROFILE": "happy",
        "CONFIDENCE_THRESHOLD": "notfloat",
    })
    with pytest.raises(ValueError):
        mod.load_config()

    # out of bounds < 0
    mod = reload_config(monkeypatch, {
        "USE_MOCKS": "true",
        "MOCK_PROFILE": "happy",
        "CONFIDENCE_THRESHOLD": "-0.1",
    })
    with pytest.raises(ValueError):
        mod.load_config()

    # out of bounds > 1
    mod = reload_config(monkeypatch, {
        "USE_MOCKS": "true",
        "MOCK_PROFILE": "happy",
        "CONFIDENCE_THRESHOLD": "1.1",
    })
    with pytest.raises(ValueError):
        mod.load_config()


def test_requires_catalog_vars_when_real(monkeypatch: pytest.MonkeyPatch):
    mod = reload_config(monkeypatch, {
        "USE_MOCKS": "false",
        # Missing CATALOG_* values should fail
    })
    with pytest.raises(ValueError) as e:
        mod.load_config()
    assert "Missing required env" in str(e.value)


def test_real_mode_ok_when_all_present(monkeypatch: pytest.MonkeyPatch):
    mod = reload_config(monkeypatch, {
        "USE_MOCKS": "false",
        "CATALOG_API_URL": "https://example/api",
        "CATALOG_API_KEY": "key",
        "CATALOG_ID": "123",
        "MOCK_PROFILE": "happy",  # still required to be valid
        "SEED": "7",
        "STREAMLIT_PORT": "8600",
        "LOG_LEVEL": "debug",
    })
    cfg = mod.load_config()
    assert cfg.use_mocks is False
    assert cfg.catalog_api_url and cfg.catalog_api_key and cfg.catalog_id
    assert cfg.seed == 7
    assert cfg.streamlit_port == 8600
    assert cfg.log_level == "DEBUG"
    # threshold default applies when not set
    assert cfg.confidence_threshold == 0.7
    # defaults when not set
    assert cfg.catalog_timeout_sec == 10.0
    assert cfg.catalog_retries == 3


def test_parses_catalog_timeout_and_retries(monkeypatch: pytest.MonkeyPatch):
    mod = reload_config(monkeypatch, {
        "USE_MOCKS": "true",
        "MOCK_PROFILE": "happy",
        "CATALOG_TIMEOUT_SEC": "5.5",
        "CATALOG_RETRIES": "7",
    })
    cfg = mod.load_config()
    assert cfg.catalog_timeout_sec == 5.5
    assert cfg.catalog_retries == 7


def test_parses_backoff_envs(monkeypatch: pytest.MonkeyPatch):
    mod = reload_config(monkeypatch, {
        "USE_MOCKS": "true",
        "MOCK_PROFILE": "happy",
        "CATALOG_BACKOFF_BASE_MS": "10",
        "CATALOG_BACKOFF_MAX_MS": "40",
        "CATALOG_BACKOFF_JITTER_MS": "0",
        "BACKOFF_BASE_MS": "20",
        "BACKOFF_MAX_MS": "80",
        "BACKOFF_JITTER_MS": "5",
    })
    cfg = mod.load_config()
    assert (cfg.catalog_backoff_base_ms, cfg.catalog_backoff_max_ms, cfg.catalog_backoff_jitter_ms) == (10, 40, 0)
    assert (cfg.backoff_base_ms, cfg.backoff_max_ms, cfg.backoff_jitter_ms) == (20, 80, 5)


def test_invalid_integer_env(monkeypatch: pytest.MonkeyPatch):
    mod = reload_config(monkeypatch, {
        "USE_MOCKS": "true",
        "MOCK_PROFILE": "happy",
        "SEED": "notint",
    })
    with pytest.raises(ValueError):
        mod.load_config()
