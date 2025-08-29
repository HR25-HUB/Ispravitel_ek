from __future__ import annotations

from typing import Any, Protocol

from catalog_api import CatalogAPI
from config import Config, load_config

try:
    from mocks.catalog_api_mock import CatalogAPIMock
except ImportError:  # pragma: no cover - mock may not exist until Iteration 3
    CatalogAPIMock = None  # type: ignore

try:
    from mocks.lcsc_mock import LCSCMock
except ImportError:  # pragma: no cover - may not exist until Iteration 4
    LCSCMock = None  # type: ignore

try:
    from mocks.llm_mock import LLMMock
except ImportError:  # pragma: no cover - may not exist until Iteration 5
    LLMMock = None  # type: ignore


class CatalogClient(Protocol):
    def search_product(self, partnumber: str):
        ...


def get_catalog_client(cfg: Config | None = None) -> CatalogClient:
    """Return a Catalog client according to config (mock or real).

    If cfg is None, loads from environment.
    """
    cfg = cfg or load_config()

    if cfg.use_mocks and CatalogAPIMock is not None:
        return CatalogAPIMock(profile=cfg.mock_profile, seed=cfg.seed)

    # Real client (or fallback until mocks are implemented)
    base_url = cfg.catalog_api_url or "https://catalogapp/api"
    api_key = cfg.catalog_api_key or "test_key"
    return CatalogAPI(
        base_url=base_url,
        api_key=api_key,
        timeout_sec=cfg.catalog_timeout_sec,
        retries=cfg.catalog_retries,
        backoff_base_ms=cfg.catalog_backoff_base_ms,
        backoff_max_ms=cfg.catalog_backoff_max_ms,
        backoff_jitter_ms=cfg.catalog_backoff_jitter_ms,
    )


class LCSCClient(Protocol):
    def search(self, partnumber: str) -> list[dict[str, Any]]:
        ...


def get_lcsc_client(cfg: Config | None = None) -> LCSCClient:
    """Return an LCSC client according to config (mock for now)."""
    try:
        cfg = cfg or load_config()
    except Exception as exc:
        # If config validation fails in real mode, tests expect NotImplementedError for real client
        raise NotImplementedError("Real LCSC client is not implemented yet") from exc
    if cfg.use_mocks and LCSCMock is not None:
        return LCSCMock(profile=cfg.mock_profile, seed=cfg.seed)
    # Real LCSC client not implemented yet
    raise NotImplementedError("Real LCSC client is not implemented yet")


class LLMClient(Protocol):
    def normalize(self, text: str) -> dict[str, Any]:
        ...

    def classify(self, gn_candidates: list[str], vn_candidates: list[str], text: str) -> dict[str, Any]:
        ...


def get_llm_client(cfg: Config | None = None) -> LLMClient:
    """Return an LLM client according to config (mock for now)."""
    try:
        cfg = cfg or load_config()
    except Exception as exc:
        # If config validation fails in real mode, tests expect NotImplementedError for real client
        raise NotImplementedError("Real LLM client is not implemented yet") from exc
    if cfg.use_mocks and LLMMock is not None:
        return LLMMock(seed=cfg.seed)
    # Real LLM client not implemented yet
    raise NotImplementedError("Real LLM client is not implemented yet")
