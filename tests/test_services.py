import pytest

from services import get_catalog_client, get_lcsc_client, get_llm_client
from config import load_config


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    # Ensure a clean environment for each test
    for key in [
        "USE_MOCKS",
        "MOCK_PROFILE",
        "SEED",
        "CATALOG_API_URL",
        "CATALOG_API_KEY",
        "CATALOG_ID",
        "CONFIDENCE_THRESHOLD",
    ]:
        monkeypatch.delenv(key, raising=False)
    yield


def test_factory_returns_mock_when_use_mocks_true(monkeypatch):
    monkeypatch.setenv("USE_MOCKS", "1")
    monkeypatch.setenv("MOCK_PROFILE", "happy")
    client = get_catalog_client()
    # Mock exposes create/update methods which real may not; minimally check type by behavior of search_product
    res = client.search_product("ABC123")
    assert isinstance(res, list)
    assert len(res) in (0, 1, 2)


def test_factory_returns_real_when_use_mocks_false(monkeypatch):
    monkeypatch.setenv("USE_MOCKS", "0")
    # Provide required real-mode vars to pass config validation
    monkeypatch.setenv("CATALOG_API_URL", "https://example/api")
    monkeypatch.setenv("CATALOG_API_KEY", "key")
    monkeypatch.setenv("CATALOG_ID", "cid")
    # Provide backoff params
    monkeypatch.setenv("CATALOG_BACKOFF_BASE_MS", "11")
    monkeypatch.setenv("CATALOG_BACKOFF_MAX_MS", "22")
    monkeypatch.setenv("CATALOG_BACKOFF_JITTER_MS", "33")

    cfg = load_config()
    client = get_catalog_client(cfg)
    # Real client performs HTTP in search_product; we won't call it here to avoid network
    # Instead, assert it has the method and does not raise during construction
    assert hasattr(client, "search_product")
    # Check backoff values propagated
    assert getattr(client, "backoff_base_ms", None) == 11
    assert getattr(client, "backoff_max_ms", None) == 22
    assert getattr(client, "backoff_jitter_ms", None) == 33


def test_get_lcsc_client_returns_mock_when_use_mocks_true(monkeypatch):
    monkeypatch.setenv("USE_MOCKS", "1")
    monkeypatch.setenv("MOCK_PROFILE", "happy")
    client = get_lcsc_client()
    res = client.search("ABC123")
    assert isinstance(res, list)


def test_get_lcsc_client_raises_when_real(monkeypatch):
    monkeypatch.setenv("USE_MOCKS", "0")
    with pytest.raises(NotImplementedError):
        get_lcsc_client()


def test_get_llm_client_returns_mock_when_use_mocks_true(monkeypatch):
    monkeypatch.setenv("USE_MOCKS", "1")
    monkeypatch.setenv("MOCK_PROFILE", "happy")
    c = get_llm_client()
    n = c.normalize("10k resistor 0603 1%")
    assert set(n).issuperset({"global_name", "local_name", "category", "attrs"})
    r = c.classify(["GN1", "GN2"], ["VN1", "VN2"], "text")
    assert set(r).issuperset({"gn", "vn", "confidence"})


def test_get_llm_client_raises_when_real(monkeypatch):
    monkeypatch.setenv("USE_MOCKS", "0")
    with pytest.raises(NotImplementedError):
        get_llm_client()
