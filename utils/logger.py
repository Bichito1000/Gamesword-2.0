"""Configuración de logs con rotación."""
import logging
import sys
from logging.handlers import RotatingFileHandler

from .paths import logs_dir, is_frozen

_CONFIGURED = False


def setup_logger(level: int = logging.INFO) -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger("gamesword")
    if _CONFIGURED:
        return logger
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = RotatingFileHandler(
        logs_dir() / "gamesword.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    if not is_frozen():
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(fmt)
        logger.addHandler(console)

    _CONFIGURED = True
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"gamesword.{name}")
