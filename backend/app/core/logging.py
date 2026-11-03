"""
Logging for the whole backend: one format, one place.

Console lines look like ``2026-10-16 22:41:05 INFO  app.ml.learning  Learning run 12: lead model kept``.
The same lines are also written to a rotating file (``LOG_FILE``, default ``backend/data/logs/app.log``; 5 files
of 5 MB), so a problem can be looked at after the window was closed.
"""

from __future__ import annotations

import contextlib
import logging
import logging.handlers
import sys
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)-7s %(name)s  %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"
_configured = {"done": False}


def setup_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    """Configure the root logger once (safe to call again: later calls only change the level)."""
    root = logging.getLogger()
    root.setLevel(level.upper())
    if _configured["done"]:
        return
    formatter = logging.Formatter(FORMAT, DATEFMT)
    # a console that cannot show a character must not stop; and every line is written at once, also when the start
    # script sends the output to backend/data/logs/api.out (a file is block-buffered: a sign-up code shown there
    # minutes late is no use to the person waiting for it)
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(errors="replace", line_buffering=True)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.handlers[:] = [console]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    # uvicorn keeps its own handlers; route its records through ours so every line has the same format
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers[:] = []
        lg.propagate = True
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)  # one line per request is noise
    for noisy in ("apscheduler", "httpx", "urllib3", "multipart", "alembic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured["done"] = True
