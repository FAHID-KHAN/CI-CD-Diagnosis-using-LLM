# src/log_setup.py - Centralized logging configuration
#
# Usage:
#   from src.log_setup import setup_logging
#   setup_logging()             # INFO to console
#   setup_logging("DEBUG")      # DEBUG to console
#   setup_logging(log_file="run.log")  # also write to file

import logging
import sys


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """Configure the root logger with a consistent format."""
    fmt = "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        datefmt=datefmt,
        handlers=handlers,
        force=True,
    )
