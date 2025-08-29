import os
import shutil
import subprocess
import time
from contextlib import contextmanager

import pytest


DOCKER_TIMEOUT = int(os.getenv("DOCKER_SMOKE_TIMEOUT", "120"))
POLL_INTERVAL = 2


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _compose_available() -> bool:
    # docker compose v2 is bundled as a subcommand
    try:
        subprocess.run(["docker", "compose", "version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


skip_reason = "Docker not available or DOCKER_SMOKE not enabled"
skip_smoke = not (_docker_available() and _compose_available() and os.getenv("DOCKER_SMOKE"))


def _run(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def _wait_healthy(container_name: str, timeout: int = DOCKER_TIMEOUT) -> None:
    deadline = time.time() + timeout
    last_status = "unknown"
    while time.time() < deadline:
        try:
            res = _run(["docker", "inspect", "-f", "{{ .State.Health.Status }}", container_name])
            last_status = res.stdout.strip()
            if last_status == "healthy":
                return
        except subprocess.CalledProcessError:
            # container may not be up yet
            pass
        time.sleep(POLL_INTERVAL)
    raise AssertionError(f"Container {container_name} health status did not become healthy in time (last: {last_status})")


@contextmanager
def compose_up(profile: str, service: str):
    try:
        _run(["docker", "compose", "--profile", profile, "up", "-d", "--build", service])
        yield
    finally:
        # Always attempt to tear down this profile stack
        try:
            _run(["docker", "compose", "--profile", profile, "down", "-v"])
        except Exception:
            pass


@pytest.mark.skipif(skip_smoke, reason=skip_reason)
def test_bot_prod_health() -> None:
    container = "bot_ispravitel_prod"
    with compose_up("prod", "bot-prod"):
        _wait_healthy(container)


@pytest.mark.skipif(skip_smoke, reason=skip_reason)
def test_ui_health() -> None:
    container = "bot_ispravitel_ui"
    # Ensure a port is provided for UI
    os.environ.setdefault("STREAMLIT_PORT", "8501")
    with compose_up("ui", "ui"):
        _wait_healthy(container)
