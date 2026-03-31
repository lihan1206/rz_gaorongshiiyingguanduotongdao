import logging
import logging.handlers
import os
from datetime import datetime
from logging.config import dictConfig
from pathlib import Path
from typing import Optional


def setup_logging(
    log_level: str = "INFO",
    log_dir: Optional[str] = None,
    enable_file_logging: bool = True,
    max_file_size: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> None:
    log_level = os.environ.get("LOG_LEVEL", log_level).upper()

    log_dir_path = Path(log_dir) if log_dir else Path(__file__).parent.parent.parent / "logs"
    if enable_file_logging:
        log_dir_path.mkdir(parents=True, exist_ok=True)

    formatters = {
        "standard": {
            "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "detailed": {
            "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(funcName)s | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "json": {
            "format": '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    }

    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": log_level,
            "stream": "ext://sys.stdout",
        },
    }

    if enable_file_logging:
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "detailed",
            "level": log_level,
            "filename": str(log_dir_path / "app.log"),
            "maxBytes": max_file_size,
            "backupCount": backup_count,
            "encoding": "utf-8",
        }
        handlers["error_file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "detailed",
            "level": "ERROR",
            "filename": str(log_dir_path / "error.log"),
            "maxBytes": max_file_size,
            "backupCount": backup_count,
            "encoding": "utf-8",
        }

    loggers = {
        "app": {
            "level": log_level,
            "handlers": ["console"] + (["file", "error_file"] if enable_file_logging else []),
            "propagate": False,
        },
        "app.services": {
            "level": log_level,
            "propagate": True,
        },
        "app.api": {
            "level": log_level,
            "propagate": True,
        },
        "app.db": {
            "level": log_level,
            "propagate": True,
        },
        "sqlalchemy.engine": {
            "level": "WARNING",
            "propagate": False,
        },
        "uvicorn": {
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.access": {
            "level": "WARNING",
            "propagate": False,
        },
    }

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": formatters,
            "handlers": handlers,
            "loggers": loggers,
            "root": {
                "handlers": ["console"] + (["file"] if enable_file_logging else []),
                "level": log_level,
            },
        }
    )

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    logger = logging.getLogger("app")
    logger.info(f"日志系统初始化完成, 日志级别: {log_level}")
    if enable_file_logging:
        logger.info(f"日志文件目录: {log_dir_path}")


class ContextFilter(logging.Filter):
    def __init__(self, context: Optional[dict] = None):
        super().__init__()
        self.context = context or {}

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in self.context.items():
            setattr(record, key, value)
        return True


class SensitiveDataFilter(logging.Filter):
    SENSITIVE_PATTERNS = [
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in self.SENSITIVE_PATTERNS:
            if pattern in message.lower():
                record.msg = self._mask_sensitive(message)
                record.args = ()
                break
        return True

    def _mask_sensitive(self, message: str) -> str:
        import re

        for pattern in self.SENSITIVE_PATTERNS:
            regex = re.compile(
                rf'({pattern}["\s:=]+)(["\']?)([^"\s,}}]+)(["\']?)',
                re.IGNORECASE,
            )
            message = regex.sub(r'\1\2***MASKED***\4', message)
        return message


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_exception(logger: logging.Logger, message: str, exc: Exception) -> None:
    logger.error(f"{message}: {type(exc).__name__}: {exc}", exc_info=True)


def log_performance(logger: logging.Logger, operation: str, duration_ms: float) -> None:
    logger.debug(f"性能统计: {operation} 耗时 {duration_ms:.2f}ms")
