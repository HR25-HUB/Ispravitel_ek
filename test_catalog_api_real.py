import types
from unittest.mock import patch

import requests

from catalog_api import CatalogAPI


def make_response(status_code=200, json_data=None):
    resp = types.SimpleNamespace()
    resp.status_code = status_code
    resp.json = lambda: (json_data if json_data is not None else [])
    return resp


def test_search_product_retries_on_timeout_then_succeeds():
    api = CatalogAPI(base_url="https://example", api_key="k", timeout_sec=0.01, retries=3)
    part = "X1"
    with patch("requests.get") as mget:
        # First two calls raise Timeout, third returns 200 with payload
        mget.side_effect = [
            requests.Timeout(),
            requests.Timeout(),
            make_response(200, json_data=[{"id": "p1", "partnumber": part}]),
        ]
        res = api.search_product(part)
        assert isinstance(res, list)
        assert res and res[0]["partnumber"] == part


def test_search_product_returns_empty_on_non_200():
    api = CatalogAPI(base_url="https://example", api_key="k", timeout_sec=0.01, retries=2)
    with patch("requests.get") as mget:
        mget.return_value = make_response(500, json_data=None)
        res = api.search_product("ANY")
        assert res == []


def test_search_product_returns_empty_after_retries():
    api = CatalogAPI(base_url="https://example", api_key="k", timeout_sec=0.01, retries=2)
    with patch("requests.get") as mget:
        mget.side_effect = [requests.Timeout(), requests.Timeout()]
        res = api.search_product("ANY")
        assert res == []


def test_search_product_backoff_sleeps_between_retries():
    # Configure small, deterministic backoff (jitter=0)
    api = CatalogAPI(
        base_url="https://example",
        api_key="k",
        timeout_sec=0.01,
        retries=3,
        backoff_base_ms=10,
        backoff_max_ms=40,
        backoff_jitter_ms=0,
    )
    with patch("requests.get") as mget, patch("catalog_api.time.sleep") as msleep:
        # Two timeouts, then success
        mget.side_effect = [requests.Timeout(), requests.Timeout(), make_response(200, json_data=[])]
        api.search_product("PN")
        # Expect sleeps: 10ms, then 20ms (exponential), both <= max 40ms
        calls = [c.args[0] for c in msleep.call_args_list]
        assert calls == [0.01, 0.02]
