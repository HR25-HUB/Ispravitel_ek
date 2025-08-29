import json
import os

import pandas as pd

from reporter import save_report


def test_save_report_creates_file_and_columns(tmp_path):
    data = [
        {
            "external_id": "ext-1",
            "partnumber": "PN1",
            "brand": "B1",
            "gn": "ГН1",
            "vn": "ВН1",
            "found_in_catalog": True,
            "action": "create",
            "status": "create",
            "reason": "not_found",
            "confidence": 0.91,
            "attrs_norm": {"k": "v"},
            "errors": "",
            "warnings": "",
        }
    ]
    out = tmp_path / "out.xlsx"
    fname = save_report(data, str(out))
    assert fname and os.path.exists(fname)

    df = pd.read_excel(fname)
    # Preferred columns should be present and ordered first
    expected_prefix = [
        "external_id",
        "partnumber",
        "brand",
        "gn",
        "vn",
        "found_in_catalog",
        "action",
        "status",
        "reason",
        "confidence",
        "attrs_norm",
        "errors",
        "warnings",
    ]
    assert df.columns.tolist()[: len(expected_prefix)] == expected_prefix

    # attrs_norm should be JSON string
    v = df.loc[0, "attrs_norm"]
    assert isinstance(v, str)
    parsed = json.loads(v) if v else {}
    assert parsed == {"k": "v"}
