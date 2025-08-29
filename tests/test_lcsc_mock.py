import pytest

from mocks.lcsc_mock import LCSCMock


@pytest.mark.parametrize("profile", ["happy", "missing", "conflict", "errorrate10", "timeout"])
def test_lcsc_search_profiles(profile: str):
    mock = LCSCMock(profile=profile, seed=123)
    part = "ABC123"

    if profile == "missing":
        assert mock.search(part) == []
    elif profile == "conflict":
        res = mock.search(part)
        assert isinstance(res, list) and len(res) == 2
        for item in res:
            assert item["partnumber"] == part
            assert set(item).issuperset({"partnumber", "brand", "category", "attrs", "datasheet_url"})
    elif profile == "happy":
        res = mock.search(part)
        assert isinstance(res, list) and len(res) == 1
        item = res[0]
        assert item["partnumber"] == part
        assert set(item).issuperset({"partnumber", "brand", "category", "attrs", "datasheet_url"})
    elif profile == "timeout":
        with pytest.raises(TimeoutError):
            mock.search(part)
    else:  # errorrate10
        for _ in range(5):
            try:
                res = mock.search(part)
                assert isinstance(res, list)
                if res:
                    assert res[0]["partnumber"] == part
                break
            except RuntimeError:
                continue
        else:
            pytest.fail("errorrate10 kept failing after retries")
