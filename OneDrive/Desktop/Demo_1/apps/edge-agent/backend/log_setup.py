"""
log_setup.py — central logger config for the edge agent.

Replaces scattered print() calls. Writes to:
  - stderr (always; uvicorn captures it)
  - logs/edge.log (rotated, 5 MB × 3 files)

Usage in any module:
    from log_setup import get_logger
    log = get_logger(__name__)
    log.info("camera started")
"""

import logging
import os
from logging.handlers import RotatingFileHandler

_BASE     = os.path.dirname(os.path.abspath(__file__))
_LOG_DIR  = os.path.abspath(os.path.join(_BASE, "..", "logs"))
_LOG_PATH = os.path.join(_LOG_DIR, "edge.log")

_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _configure():
    global _configured
    if _configured:
        return
    os.makedirs(_LOG_DIR, exist_ok=True)

    root = logging.getLogger("mergen")
    root.setLevel(logging.INFO)
    root.propagate = False

    # Stream handler (uvicorn picks this up)
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter(_FMT, _DATEFMT))
    root.addHandler(sh)

    # Rotating file handler — 5 MB × 3 files = 15 MB max
    try:
        fh = RotatingFileHandler(_LOG_PATH, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(logging.Formatter(_FMT, _DATEFMT))
        root.addHandler(fh)
    except Exception as e:
        # Non-fatal: keep going without file logs if dir isn't writable
        print(f"[log_setup] file handler failed: {e}")

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'mergen' namespace."""
    _configure()
    short = name.replace("apps.edge-agent.backend.", "").replace("backend.", "")
    return logging.getLogger("mergen." + short)
