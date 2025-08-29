import subprocess

import agent


def test_agent_job_runs_subprocess_success(monkeypatch):
    calls = {}

    def fake_run(cmd, check):
        calls["cmd"] = cmd
        calls["check"] = check
        return None

    monkeypatch.setattr(subprocess, "run", fake_run)

    # Should not raise
    agent.job()

    assert calls.get("cmd") == ["python", "main.py"]
    assert calls.get("check") is True


def test_agent_job_logs_error_on_failure(monkeypatch, caplog):
    def fake_run_fail(cmd, check):
        raise subprocess.CalledProcessError(returncode=2, cmd=cmd)

    monkeypatch.setattr(subprocess, "run", fake_run_fail)

    with caplog.at_level("INFO"):
        # Should not raise; error is logged inside job()
        agent.job()

    # Ensure an error was logged about failure
    assert any("ошибка запуска main.py" in rec.getMessage() for rec in caplog.records)
