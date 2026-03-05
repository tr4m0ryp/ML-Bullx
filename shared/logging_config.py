"""Centralized logging setup for all pipeline modules."""
import logging
import sys


def setup_logging(
    name: str = "ml_bullx",
    level: int = logging.INFO,
    log_file: str = None,
):
    """Configure logging with console and optional file output.

    Call once at each entry point (CLI script). Modules should use
    ``logging.getLogger(__name__)`` and never call basicConfig themselves.
    """
    fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    handlers = [logging.StreamHandler(sys.stderr)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(level=level, format=fmt, handlers=handlers)
    return logging.getLogger(name)
