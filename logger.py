from __future__ import annotations

import logging
import os
import sys
import uuid
from datetime import datetime
from typing import Tuple

_RUN_ID: str | None = None
_INITIALIZED = False


def generate_run_id() -> str:
    global _RUN_ID
    if _RUN_ID:
        return _RUN_ID
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    rnd = uuid.uuid4().hex[:8]
    _RUN_ID = f"run-{ts}-{rnd}"
    return _RUN_ID


def init_logging(level: str = "INFO", run_id: str | None = None, log_dir: str = "logs") -> Tuple[logging.Logger, str]:
    """
    Initialize root logging once with console + file handlers and a unified format.
    Returns the root logger and the run_id used.
    """
    global _INITIALIZED, _RUN_ID
    if run_id:
        _RUN_ID = run_id
    run_id = generate_run_id()

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not _INITIALIZED:
        # Ensure directory exists
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception:
            # Fall back to current directory if cannot create
            log_dir = "."

        fmt = logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(run_id)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        class RunIdFilter(logging.Filter):
            def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
                record.run_id = run_id  # type: ignore[attr-defined]
                return True

        # Console handler
        ch = logging.StreamHandler(stream=sys.stdout)
        ch.setFormatter(fmt)
        ch.addFilter(RunIdFilter())
        root.addHandler(ch)

        # File handler
        logfile = os.path.join(log_dir, f"{run_id}.log")
        fh = logging.FileHandler(logfile, encoding="utf-8")
        fh.setFormatter(fmt)
        fh.addFilter(RunIdFilter())
        root.addHandler(fh)

        _INITIALIZED = True

    else:
        # Already initialized: still ensure a file handler for the requested run_id/log_dir exists
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception:
            log_dir = "."

        existing_files = set()
        for h in root.handlers:
            if isinstance(h, logging.FileHandler):
                try:
                    existing_files.add(os.path.abspath(h.baseFilename))  # type: ignore[attr-defined]
                except Exception:
                    pass

        target_log = os.path.abspath(os.path.join(log_dir, f"{run_id}.log"))
        if target_log not in existing_files:
            fmt = logging.Formatter(
                fmt="%(asctime)s %(levelname)s [%(run_id)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )

            class RunIdFilter(logging.Filter):
                def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
                    record.run_id = run_id  # type: ignore[attr-defined]
                    return True

            fh = logging.FileHandler(target_log, encoding="utf-8")
            fh.setFormatter(fmt)
            fh.addFilter(RunIdFilter())
            root.addHandler(fh)

    logger = logging.getLogger("app")
    return logger, run_id


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Get a logger. Ensure logging is initialized at least with defaults.
    """
    if not _INITIALIZED:
        init_logging()
    return logging.getLogger(name or "app")
