import pytest

from mocks.catalog_api_mock import CatalogAPIMock


@pytest.mark.parametrize("profile", ["happy", "missing", "conflict", "errorrate10", "timeout"])
def test_search_profiles_dont_crash(profile: str):
    mock = CatalogAPIMock(profile=profile, seed=123)
    part = "ABC123"
    if profile == "missing":
        assert mock.search_product(part) == []
    elif profile == "conflict":
        res = mock.search_product(part)
        assert isinstance(res, list) and len(res) == 2
        assert res[0]["partnumber"] == part and res[1]["partnumber"] == part
        assert "id" in res[0] and "id" in res[1]
    elif profile == "happy":
        res = mock.search_product(part)
        assert isinstance(res, list) and len(res) == 1
        assert res[0]["partnumber"] == part
        assert "id" in res[0]
    elif profile == "timeout":
        with pytest.raises(TimeoutError):
            mock.search_product(part)
    else:  # errorrate10
        # Might raise ~10% of the time, retry a few times to observe non-error path deterministically
        for _ in range(5):
            try:
                res = mock.search_product(part)
                assert isinstance(res, list) and len(res) in (0, 1, 2)
                if res:
                    assert "id" in res[0]
                break
            except RuntimeError:
                continue
        else:
            pytest.fail("errorrate10 kept failing after retries")


def test_create_update_basic():
    mock = CatalogAPIMock(profile="happy", seed=1)
    created = mock.create_product({"partnumber": "NEW123", "name": "X", "brand": "Y"})
    assert created["status"] == "created"
    assert created["id"]

    updated = mock.update_product(created["id"], {"name": "X2"})
    assert updated["status"] == "updated"
    assert updated["id"] == created["id"]


def test_timeout_profile_raises_on_create_update():
    mock = CatalogAPIMock(profile="timeout", seed=7)
    with pytest.raises(TimeoutError):
        mock.create_product({"partnumber": "NEW1"})
    with pytest.raises(TimeoutError):
        mock.update_product("id-1", {"brand": "B"})
