"""Logging configuration module for QDII ETF Premium Monitor."""

import logging
import os
import sys
from datetime import datetime


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Set up application logging with file and console handlers.

    Creates a logger that writes to both stderr (console) and a daily log file
    in the logs/ directory with the format: YYYY-MM-DD HH:MM:SS LEVEL [Module] message

    Args:
        level: Logging level string (DEBUG, INFO, WARNING, ERROR). Defaults to "INFO".

    Returns:
        Configured root logger instance.
    """
    # Ensure logs/ directory exists
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(logs_dir, exist_ok=True)

    # Determine log level
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Create logger
    logger = logging.getLogger("monitor")
    logger.setLevel(log_level)

    # Avoid adding duplicate handlers if called multiple times
    if logger.handlers:
        return logger

    # Log format: YYYY-MM-DD HH:MM:SS LEVEL [Module] message
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler - daily rotation via filename
    log_filename = f"monitor_{datetime.now().strftime('%Y%m%d')}.log"
    log_filepath = os.path.join(logs_dir, log_filename)
    file_handler = logging.FileHandler(log_filepath, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)

    # Console handler - writes to stderr
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
