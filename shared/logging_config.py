"""
Centralized Logging Configuration for the ML-Bullx Pipeline.

Provides a single ``setup_logging`` function that each CLI entry point should
call exactly once. Individual modules must use ``logging.getLogger(__name__)``
and never configure the root logger themselves.

Author: ML-Bullx Team
Date: 2025-08-01
"""
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

    Args:
        name: Logger name returned to the caller.
        level: Logging threshold (default: INFO).
        log_file: Optional path to a log file. When provided, a
            FileHandler is attached alongside the console handler.

    Returns:
        Configured ``logging.Logger`` instance.
    """
    fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    handlers = [logging.StreamHandler(sys.stderr)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(level=level, format=fmt, handlers=handlers)
    return logging.getLogger(name)
