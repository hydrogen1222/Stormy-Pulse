"""Logging setup shared by the desktop and WebUI entry points."""
import logging


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logging once, at program start (not at import time)."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
