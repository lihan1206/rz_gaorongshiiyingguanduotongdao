import os
import logging
from logging.config import dictConfig
from logging.handlers import RotatingFileHandler

from app.core.config import AppConfig


def setup_logging() -> None:
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    system_config = AppConfig.get("system", {})
    log_level = system_config.get("log_level", "INFO").upper()
    max_log_size = system_config.get("max_log_size_mb", 100) * 1024 * 1024
    backup_count = system_config.get("log_retention_days", 30)

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
                },
                "detailed": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(module)s:%(lineno)d | %(message)s"
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "level": log_level,
                },
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": os.path.join(log_dir, "app.log"),
                    "formatter": "detailed",
                    "level": log_level,
                    "maxBytes": max_log_size,
                    "backupCount": backup_count,
                    "encoding": "utf-8",
                },
                "error_file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": os.path.join(log_dir, "error.log"),
                    "formatter": "detailed",
                    "level": "ERROR",
                    "maxBytes": max_log_size,
                    "backupCount": backup_count,
                    "encoding": "utf-8",
                },
            },
            "root": {
                "handlers": ["console", "file", "error_file"],
                "level": log_level,
            },
        }
    )
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
