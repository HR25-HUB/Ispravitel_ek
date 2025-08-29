import os

from logger import init_logging
from reporter import save_report


def test_logging_creates_file_and_contains_run_id(tmp_path):
    run_id = "test-run-id"
    log_dir = tmp_path / "logs"
    logger, used_run_id = init_logging("INFO", run_id=run_id, log_dir=str(log_dir))
    assert used_run_id == run_id
    logger.info("hello world")

    logfile = log_dir / f"{run_id}.log"
    assert logfile.exists()

    content = logfile.read_text(encoding="utf-8")
    assert run_id in content
    assert "INFO" in content
    assert "hello world" in content


def test_report_filename_contains_run_id(tmp_path):
    run_id = "report-run-id"
    # Re-init to set new run id and ensure directory exists
    init_logging("INFO", run_id=run_id, log_dir=str(tmp_path / "logs2"))

    data = [{"partnumber": "PN", "status": "skip", "reason": "test"}]
    fname = save_report(data)
    assert fname is not None
    assert os.path.basename(fname) == f"report_{run_id}.xlsx"
    assert os.path.exists(fname)
