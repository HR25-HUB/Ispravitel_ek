import importlib
import os
from typing import Callable

import pytest

import agent as agent_module
import config as config_module


def reload_config_for_schedule(monkeypatch: pytest.MonkeyPatch, schedule_value: str):
    # Minimal env to pass validation
    base_env = {
        "USE_MOCKS": "true",
        "MOCK_PROFILE": "happy",
        "LOG_LEVEL": "INFO",
        "AGENT_SCHEDULE": schedule_value,
    }
    for k in list(os.environ.keys()):
        if k in base_env or k in {"USE_MOCKS", "MOCK_PROFILE", "LOG_LEVEL", "AGENT_SCHEDULE"}:
            monkeypatch.delenv(k, raising=False)
    for k, v in base_env.items():
        monkeypatch.setenv(k, v)
    return importlib.reload(config_module)


def test_config_invalid_schedule(monkeypatch: pytest.MonkeyPatch):
    # Invalid formats
    for invalid in ["3:7", "24:00", "12:60", "", "aa:bb", "1234"]:
        with pytest.raises(ValueError):
            mod = reload_config_for_schedule(monkeypatch, invalid)
            mod.load_config()


def test_config_valid_schedule(monkeypatch: pytest.MonkeyPatch):
    mod = reload_config_for_schedule(monkeypatch, "23:59")
    cfg = mod.load_config()
    assert cfg.agent_schedule == "23:59"


class FakeSchedule:
    def __init__(self):
        self._job: Callable[[], None] | None = None
        self.run_calls = 0

    # API similar to schedule.every().day.at(...).do(job)
    def every(self):
        return self

    @property
    def day(self):
        return self

    def at(self, _when: str):
        return self

    def do(self, fn: Callable[[], None]):
        self._job = fn
        return self

    def run_pending(self):
        self.run_calls += 1
        if self._job:
            self._job()


def test_agent_setup_and_loop(monkeypatch: pytest.MonkeyPatch, caplog):
    # Prepare fake schedule and a stub for subprocess.run to avoid real call
    calls = {"ran": 0}

    def fake_subprocess_run(cmd, check):
        calls["ran"] += 1
        return None

    monkeypatch.setattr(agent_module.subprocess, "run", fake_subprocess_run)

    fs = FakeSchedule()
    agent_module.setup_schedule(fs, "12:34")

    # Run exactly 1 iteration without sleeping
    agent_module._run_pending_loop(fs, iterations=1, sleep_seconds=0, sleep_fn=lambda _: None)

    assert fs.run_calls == 1
    assert calls["ran"] == 1
