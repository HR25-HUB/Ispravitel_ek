from import_excel import validate_input


def test_missing_partnumber():
    rows = [
        {"partnumber": None, "brand": "B1"},
        {"brand": "B2"},
        {"partnumber": "   ", "brand": "B3"},
    ]
    valid, invalid = validate_input(rows)
    assert len(valid) == 0
    assert len(invalid) == 3
    for r in invalid:
        assert r["status"] == "skip"
        assert r["reason"] == "invalid_input:missing_partnumber"
        assert "validation:missing_partnumber" in r.get("errors", "")


def test_duplicate_partnumber():
    rows = [
        {"partnumber": "ABC-123", "brand": "B1"},
        {"partnumber": "abc-123", "brand": "B2"},  # duplicate (case-insensitive)
    ]
    valid, invalid = validate_input(rows)
    assert len(valid) == 1
    assert len(invalid) == 1
    assert valid[0]["partnumber"] == "ABC-123"
    dup = invalid[0]
    assert dup["status"] == "skip"
    assert dup["reason"] == "invalid_input:duplicate_partnumber"
    assert "validation:duplicate_partnumber" in dup.get("errors", "")


def test_missing_brand_warning():
    rows = [
        {"partnumber": "PN-1", "brand": None},
        {"partnumber": "PN-2", "brand": "   "},
    ]
    valid, invalid = validate_input(rows)
    assert len(invalid) == 0
    assert len(valid) == 2
    for r in valid:
        assert r["partnumber"].startswith("PN-")
        assert "validation:missing_brand" in r.get("warnings", "")
