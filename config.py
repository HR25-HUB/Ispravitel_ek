from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

VALID_MOCK_PROFILES = {"happy", "conflict", "missing", "errorrate10", "timeout"}


@dataclass(frozen=True)
class Config:
    # CatalogApp
    catalog_api_url: Optional[str]
    catalog_api_key: Optional[str]
    catalog_id: Optional[str]
    catalog_timeout_sec: float
    catalog_retries: int
    catalog_backoff_base_ms: int
    catalog_backoff_max_ms: int
    catalog_backoff_jitter_ms: int

    # LLM / Coze
    coze_api_url: Optional[str]
    coze_api_key: Optional[str]
    confidence_threshold: float

    # Mocks and determinism
    use_mocks: bool
    mock_profile: str
    seed: int

    # UI/Runtime
    streamlit_port: int
    log_level: str

    # Agent
    agent_schedule: str  # e.g. "03:00"
    input_path: Optional[str]
    # Generic backoff for pipeline retries
    backoff_base_ms: int
    backoff_max_ms: int
    backoff_jitter_ms: int

    @property
    def is_catalog_required(self) -> bool:
        return not self.use_mocks


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Env {name} must be integer, got: {raw}") from exc


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Env {name} must be float, got: {raw}") from exc


def _validate(cfg: Config) -> None:
    # Validate mock profile
    if cfg.mock_profile not in VALID_MOCK_PROFILES:
        raise ValueError(
            f"MOCK_PROFILE must be one of {sorted(VALID_MOCK_PROFILES)}, got: {cfg.mock_profile}"
        )

    # Validate required when not using mocks
    if not cfg.use_mocks:
        missing = [
            k
            for k, v in {
                "CATALOG_API_URL": cfg.catalog_api_url,
                "CATALOG_API_KEY": cfg.catalog_api_key,
                "CATALOG_ID": cfg.catalog_id,
            }.items()
            if not v
        ]
        if missing:
            raise ValueError(
                "Missing required env(s) for real CatalogApp integration: " + ", ".join(missing)
            )

    # Basic log level validation
    allowed_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if cfg.log_level.upper() not in allowed_levels:
        raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed_levels)}")

    # Confidence threshold 0..1
    if not (0.0 <= cfg.confidence_threshold <= 1.0):
        raise ValueError("CONFIDENCE_THRESHOLD must be between 0.0 and 1.0")

    # Agent schedule HH:MM basic validation
    if not re.fullmatch(r"\d{2}:\d{2}", cfg.agent_schedule or ""):
        raise ValueError("AGENT_SCHEDULE must be in HH:MM format, e.g. 03:00")
    try:
        hh, mm = cfg.agent_schedule.split(":")
        h, m = int(hh), int(mm)
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError("AGENT_SCHEDULE must have valid hour/minute values") from exc


def load_config(override_dotenv_path: Optional[str] = None) -> Config:
    """
    Load configuration from .env/environment with sane defaults and validation.
    If override_dotenv_path is provided, it will be used instead of default resolution.
    """
    # Load .env once per process; allow overriding in tests
    load_dotenv(dotenv_path=override_dotenv_path, override=False)

    use_mocks = _get_bool("USE_MOCKS", True)
    mock_profile = os.getenv("MOCK_PROFILE", "happy").strip().lower()
    seed = _get_int("SEED", 42)

    cfg = Config(
        # Catalog
        catalog_api_url=os.getenv("CATALOG_API_URL"),
        catalog_api_key=os.getenv("CATALOG_API_KEY"),
        catalog_id=os.getenv("CATALOG_ID"),
        catalog_timeout_sec=_get_float("CATALOG_TIMEOUT_SEC", 10.0),
        catalog_retries=_get_int("CATALOG_RETRIES", 3),
        catalog_backoff_base_ms=_get_int("CATALOG_BACKOFF_BASE_MS", 100),
        catalog_backoff_max_ms=_get_int("CATALOG_BACKOFF_MAX_MS", 2000),
        catalog_backoff_jitter_ms=_get_int("CATALOG_BACKOFF_JITTER_MS", 100),
        # Coze
        coze_api_url=os.getenv("COZE_API_URL"),
        coze_api_key=os.getenv("COZE_API_KEY"),
        confidence_threshold=_get_float("CONFIDENCE_THRESHOLD", 0.7),
        # Mocks
        use_mocks=use_mocks,
        mock_profile=mock_profile,
        seed=seed,
        # UI/Runtime
        streamlit_port=_get_int("STREAMLIT_PORT", 8501),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        # Agent
        agent_schedule=os.getenv("AGENT_SCHEDULE", "03:00"),
        input_path=os.getenv("INPUT_PATH"),
        backoff_base_ms=_get_int("BACKOFF_BASE_MS", 100),
        backoff_max_ms=_get_int("BACKOFF_MAX_MS", 2000),
        backoff_jitter_ms=_get_int("BACKOFF_JITTER_MS", 100),
    )

    _validate(cfg)
    return cfg
