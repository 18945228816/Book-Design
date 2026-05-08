import logging
import os
from logging.handlers import TimedRotatingFileHandler

from .config import settings

_initialized = False
_access_logger = None


def _setup():
    global _initialized, _access_logger
    if _initialized:
        return
    _initialized = True

    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), settings.LOG_DIR)
    os.makedirs(log_dir, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Root logger — app.log + console
    root = logging.getLogger()
    root.setLevel(level)

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(fmt)
    root.addHandler(console)

    app_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        when="midnight",
        backupCount=settings.LOG_RETENTION_DAYS,
        encoding="utf-8",
    )
    app_handler.setLevel(level)
    app_handler.setFormatter(fmt)
    app_handler.suffix = "%Y-%m-%d"
    root.addHandler(app_handler)

    # error.log — ERROR+ only
    error_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, "error.log"),
        when="midnight",
        backupCount=settings.LOG_RETENTION_DAYS,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(fmt)
    error_handler.suffix = "%Y-%m-%d"
    root.addHandler(error_handler)

    # access.log — dedicated request logger
    _access_logger = logging.getLogger("access")
    _access_logger.setLevel(level)
    _access_logger.propagate = False

    access_fmt = logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    access_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, "access.log"),
        when="midnight",
        backupCount=settings.LOG_RETENTION_DAYS,
        encoding="utf-8",
    )
    access_handler.setFormatter(access_fmt)
    access_handler.suffix = "%Y-%m-%d"
    _access_logger.addHandler(access_handler)

    # Also add console handler for access logger
    access_console = logging.StreamHandler()
    access_console.setFormatter(access_fmt)
    _access_logger.addHandler(access_console)

    # Suppress uvicorn access logs (we have our own)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    _setup()
    return logging.getLogger(name)


def get_access_logger() -> logging.Logger:
    _setup()
    return _access_logger
