"""Persistent rolling logs and native Python crash traces."""

from pathlib import Path
from logging.handlers import RotatingFileHandler
import faulthandler
import logging
import os
import sys

_crash_stream = None


def log_directory() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "PanoTess"
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PanoTess" / "logs"


def setup_logging() -> Path:
    global _crash_stream
    root = log_directory()
    root.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(root / "panotess.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    crash = root / "crash.log"
    if crash.exists() and crash.stat().st_size > 2_000_000:
        crash.replace(root / "crash.previous.log")
    _crash_stream = crash.open("a", encoding="utf-8")
    faulthandler.enable(file=_crash_stream, all_threads=True)
    logging.info("PanoTess starting | Python %s | %s", sys.version.split()[0], sys.platform)
    return root
