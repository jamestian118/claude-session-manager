"""Logging configuration helpers for CSM."""

from __future__ import annotations

import logging
import os

_DEFAULT_LEVEL_NAME = "WARNING"
_LEVEL_MAP = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


def _resolve_level(raw_value: str | None) -> tuple[int, bool]:
    raw = (raw_value or "").strip()
    if not raw:
        return _LEVEL_MAP[_DEFAULT_LEVEL_NAME], False

    upper = raw.upper()
    if upper in _LEVEL_MAP:
        return _LEVEL_MAP[upper], False

    if raw.lstrip("-").isdigit():
        return int(raw), False

    return _LEVEL_MAP[_DEFAULT_LEVEL_NAME], True


def configure_logging() -> int:
    """Configure root logging level from CSM_LOG_LEVEL env var."""
    raw = os.environ.get("CSM_LOG_LEVEL", "")
    level, invalid = _resolve_level(raw)

    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
        for handler in root.handlers:
            handler.setLevel(level)
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )

    logger = logging.getLogger(__name__)
    if invalid:
        logger.warning(
            "Invalid CSM_LOG_LEVEL=%r, fallback to %s",
            raw,
            _DEFAULT_LEVEL_NAME,
        )
    return level
