import os
import subprocess

import pandas as pd

from import_excel import load_excel
from reporter import save_report


def test_load_excel(tmp_path):
    file = tmp_path / "test.xlsx"
    df = pd.DataFrame([{"partnumber": "TST001", "brand": "TestBrand"}])
    df.to_excel(file, index=False)

    records = load_excel(str(file))
    assert len(records) == 1
    assert records[0]["partnumber"] == "TST001"

def test_save_report(tmp_path):
    data = [
        {"partnumber": "AAA111", "brand": "BrandA", "status": "OK"},
        {"partnumber": "BBB222", "brand": "BrandB", "status": "FAIL"}
    ]
    file = tmp_path / "report.xlsx"
    save_report(data, str(file))
    assert os.path.exists(file)
    df = pd.read_excel(file)
    assert "status" in df.columns
    assert df.shape[0] == 2

def test_main_generates_report(tmp_path):
    # Копируем sample.xlsx во временную папку
    sample_src = os.path.join(os.path.dirname(__file__), "sample.xlsx")
    sample_copy = tmp_path / "sample.xlsx"
    pd.read_excel(sample_src).to_excel(sample_copy, index=False)

    # Запуск main.py
    result = subprocess.run(["python", "main.py"], capture_output=True, text=True)
    assert result.returncode == 0

    # Проверяем, что создан отчет (в корне или в папке reports/)
    reports_root = [f for f in os.listdir() if f.startswith("report_") and f.endswith(".xlsx")]
    reports_dir = []
    if os.path.isdir("reports"):
        reports_dir = [f for f in os.listdir("reports") if f.startswith("report_") and f.endswith(".xlsx")]
    assert len(reports_root) + len(reports_dir) > 0
