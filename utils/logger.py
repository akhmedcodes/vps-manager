"""
vps-manager/utils/logger.py
Simple structured logger for vps-manager.
"""

import os
import logging
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR  = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "vps-manager.log")


def setup_logger() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger("vps-manager")
    if logger.handlers:
        return logger  # Already configured

    logger.setLevel(logging.DEBUG)

    # File handler
    fh = logging.FileHandler(LOG_FILE)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(fh)

    return logger


def log(message: str, level: str = "info") -> None:
    logger = setup_logger()
    fn = getattr(logger, level.lower(), logger.info)
    fn(message)


def get_log_tail(n: int = 50) -> str:
    """Return last n lines of the log file."""
    if not os.path.exists(LOG_FILE):
        return "(no log file yet)"
    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
        return "".join(lines[-n:]).strip()
    except Exception:
        return "(could not read log file)"