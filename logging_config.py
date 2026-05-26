"""Central logging configuration for the Brain project."""

import logging
import os
from typing import Optional


def setup_logging(level: Optional[str] = None) -> None:
    """
    Configure logging for the entire project.

    Recommended levels:
        - INFO  : Normal operation (recommended default)
        - DEBUG : Detailed ontology resolution steps
    """
    log_level_str = (level or os.getenv("BRAIN_LOG_LEVEL", "INFO")).upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # Only configure if no handlers are set yet (prevents duplicate logs)
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )

    # Reduce noise from NLTK
    logging.getLogger("nltk").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Helper to get a properly configured logger."""
    setup_logging()  # Safe to call multiple times
    return logging.getLogger(name)
