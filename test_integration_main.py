from typing import Any, Dict, List

import pytest

import main as app


class FakeCatalog:
    def __init__(self, found: Dict[str, Dict[str, Any]] | None = None):
        self.found = found or {}
        self.updated = []
        self.created = []

    def search_product(self, part: str) -> List[Dict[str, Any]]:
        if part in self.found:
            item = self.found[part].copy()
            item.setdefault("id", f"id-{part}")
            return [item]
        return []

    def update_product(self, pid: str, payload: Dict[str, Any]) -> None:
        self.updated.append((pid, payload))

    def create_product(self, payload: Dict[str, Any]) -> None:
        self.created.append(payload)


class FakeLCSC:
    def __init__(self, brand: str = "LCSCBrand"):
        self.brand = brand

    def search(self, part: str) -> List[Dict[str, Any]]:
        return [{"brand": self.brand, "part": part}]


class FakeLLM:
    def __init__(self, confidence: float):
        self.confidence = confidence

    def normalize(self, text: str) -> Dict[str, Any]:
        return {"local_name": text.lower(), "attrs": {}}

    def classify(self, gn_candidates, vn_candidates, _text: str) -> Dict[str, Any]:
        return {"gn": gn_candidates[0], "vn": vn_candidates[0], "confidence": self.confidence}


@pytest.fixture(autouse=True)
def env_mocks(monkeypatch):
    # Ensure mock mode with defaults
    monkeypatch.setenv("USE_MOCKS", "1")
    monkeypatch.delenv("CONFIDENCE_THRESHOLD", raising=False)
    yield


def run_with_rows(rows: List[Dict[str, Any]], catalog: FakeCatalog, llm_conf: float) -> List[Dict[str, Any]]:
    captured_report: List[Dict[str, Any]] = []

    # Patch imports used directly in main.py
    def fake_load_excel(_: str):
        return rows

    def fake_save_report(data):
        captured_report.extend(data)

    app.get_catalog_client = lambda cfg: catalog  # type: ignore[attr-defined]
    app.get_lcsc_client = lambda cfg: FakeLCSC()  # type: ignore[attr-defined]
    app.get_llm_client = lambda cfg: FakeLLM(llm_conf)  # type: ignore[attr-defined]
    app.load_excel = fake_load_excel  # type: ignore[attr-defined]
    app.save_report = fake_save_report  # type: ignore[attr-defined]

    app.main()
    return captured_report


def test_skip_when_already_present_same_brand():
    rows = [{"partnumber": "ABC123", "brand": "BrandA"}]
    catalog = FakeCatalog(found={"ABC123": {"brand": "BrandA"}})
    report = run_with_rows(rows, catalog, llm_conf=0.9)

    assert len(report) == 1
    assert report[0]["status"] == "skip"
    assert report[0]["reason"] == "already_present"


def test_update_when_brand_mismatch():
    rows = [{"partnumber": "ABC999", "brand": "BrandX"}]
    catalog = FakeCatalog(found={"ABC999": {"brand": "BrandY"}})
    report = run_with_rows(rows, catalog, llm_conf=0.9)

    assert len(report) == 1
    assert report[0]["status"] == "update"
    assert report[0]["reason"] == "brand_mismatch"
    # Ensure update called
    assert catalog.updated and catalog.updated[0][1]["brand"] == "BrandX"


def test_create_when_not_found_with_high_confidence():
    rows = [{"partnumber": "NEW1", "brand": ""}]
    catalog = FakeCatalog(found={})
    report = run_with_rows(rows, catalog, llm_conf=0.95)

    assert len(report) == 1
    assert report[0]["status"] == "create"
    assert report[0]["reason"] == "not_found"
    # Ensure create called
    assert catalog.created and catalog.created[0]["partnumber"] == "NEW1"


def test_skip_when_low_confidence():
    rows = [{"partnumber": "NEW2", "brand": ""}]
    catalog = FakeCatalog(found={})
    # Below default threshold 0.7
    report = run_with_rows(rows, catalog, llm_conf=0.3)

    assert len(report) == 1
    assert report[0]["status"] == "skip"
    assert report[0]["reason"] == "low_confidence"


def test_skip_when_no_partnumber():
    rows = [{"partnumber": "", "brand": "B"}]
    catalog = FakeCatalog(found={})
    report = run_with_rows(rows, catalog, llm_conf=0.9)

    assert len(report) == 1
    assert report[0]["status"] == "skip"
    # Now flagged at validation stage
    assert report[0]["reason"] == "invalid_input:missing_partnumber"


def test_retry_on_transient_create_errors(monkeypatch):
    class TransientCreateCatalog(FakeCatalog):
        def __init__(self):
            super().__init__(found={})
            self.create_calls = 0

        def search_product(self, part: str):
            return []  # Force create path

        def create_product(self, payload: Dict[str, Any]) -> None:
            self.create_calls += 1
            # Fail first two attempts to exercise retries
            if self.create_calls < 3:
                raise RuntimeError("simulated transient create error")
            self.created.append(payload)

    rows = [{"partnumber": "RTRY1", "brand": "B"}]
    catalog = TransientCreateCatalog()
    report = run_with_rows(rows, catalog, llm_conf=0.95)

    assert len(report) == 1
    assert report[0]["status"] == "create"
    assert report[0]["reason"] == "not_found"
    # Ensure 3 attempts were made and final succeeded
    assert catalog.create_calls == 3
    assert catalog.created and catalog.created[0]["partnumber"] == "RTRY1"
    # Errors should contain tags for failed attempts
    errs = report[0].get("errors", "")
    assert "catalog_create:RuntimeError:attempt1" in errs
    assert "catalog_create:RuntimeError:attempt2" in errs
