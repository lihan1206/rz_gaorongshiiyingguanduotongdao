import json
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Base exception for configuration-related errors"""
    pass


class JSONParseError(ConfigError):
    """Exception raised for JSON parsing errors"""
    pass


class Settings(BaseSettings):
    app_name: str = "高融石英管多通道液位同步检测系统"
    db_host: str = "db"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = "root"
    db_name: str = "quartz_monitor"
    cors_origins: str = "*"
    config_file_path: str = "config.json"
    thresholds_file_path: str = "thresholds.json"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def sqlalchemy_database_uri(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}@"
            f"{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


settings = Settings()


class AppConfig:
    _config: Dict[str, Any] = {}
    _thresholds: Dict[str, Any] = {}
    _last_config_modified: float = 0
    _last_thresholds_modified: float = 0
    _auto_reload_enabled: bool = True

    @classmethod
    def load_config(cls, force_reload: bool = False) -> None:
        if not force_reload and not cls._should_reload_config():
            return

        try:
            file_path = settings.config_file_path
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    try:
                        cls._config = json.load(f)
                        cls._last_config_modified = os.path.getmtime(file_path)
                        logger.info(f"配置文件已加载: {file_path}")
                    except json.JSONDecodeError as e:
                        logger.error(f"配置文件 JSON 解析错误: {e}")
                        raise JSONParseError(f"配置文件 {file_path} 解析失败: {e}") from e
            else:
                logger.warning(f"配置文件不存在，使用默认配置: {file_path}")
                cls._config = cls._get_default_config()
                cls.save_config()
        except IOError as e:
            logger.error(f"读取配置文件失败: {e}")
            raise ConfigError(f"无法读取配置文件: {e}") from e

    @classmethod
    def load_thresholds(cls, force_reload: bool = False) -> None:
        if not force_reload and not cls._should_reload_thresholds():
            return

        try:
            file_path = settings.thresholds_file_path
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    try:
                        cls._thresholds = json.load(f)
                        cls._last_thresholds_modified = os.path.getmtime(file_path)
                        logger.info(f"阈值配置已加载: {file_path}")
                    except json.JSONDecodeError as e:
                        logger.error(f"阈值配置 JSON 解析错误: {e}")
                        raise JSONParseError(f"阈值配置文件 {file_path} 解析失败: {e}") from e
            else:
                logger.warning(f"阈值配置文件不存在，使用默认阈值: {file_path}")
                cls._thresholds = cls._get_default_thresholds()
                cls.save_thresholds()
        except IOError as e:
            logger.error(f"读取阈值配置失败: {e}")
            raise ConfigError(f"无法读取阈值配置文件: {e}") from e

    @classmethod
    def _should_reload_config(cls) -> bool:
        if not cls._auto_reload_enabled:
            return False
        if not os.path.exists(settings.config_file_path):
            return True
        return os.path.getmtime(settings.config_file_path) > cls._last_config_modified

    @classmethod
    def _should_reload_thresholds(cls) -> bool:
        if not cls._auto_reload_enabled:
            return False
        if not os.path.exists(settings.thresholds_file_path):
            return True
        return os.path.getmtime(settings.thresholds_file_path) > cls._last_thresholds_modified

    @classmethod
    def _get_default_config(cls) -> Dict[str, Any]:
        return {
            "sensor_weights": {"capacitive": 0.6, "ultrasonic": 0.4},
            "alarm_settings": {
                "consecutive_threshold": 3,
                "drift_detection_window": 5,
                "drift_rate_threshold": 0.1
            },
            "sampling": {"frequency_ms": 100, "max_channels": 8},
            "system": {
                "log_level": "INFO",
                "max_log_size_mb": 100,
                "log_retention_days": 30
            }
        }

    @classmethod
    def _get_default_thresholds(cls) -> Dict[str, Any]:
        return {
            "global": {
                "warning_low": 10.0,
                "warning_high": 90.0,
                "drift_threshold": 0.5,
                "drift_time_window": 5
            },
            "channels": {
                "1": {
                    "warning_low": 10.0,
                    "warning_high": 90.0,
                    "drift_threshold": 0.5,
                    "drift_time_window": 5,
                    "enabled": True
                }
            }
        }

    @classmethod
    def save_config(cls) -> None:
        try:
            with open(settings.config_file_path, "w", encoding="utf-8") as f:
                json.dump(cls._config, f, indent=2, ensure_ascii=False)
            cls._last_config_modified = os.path.getmtime(settings.config_file_path)
            logger.info(f"配置文件已保存: {settings.config_file_path}")
        except IOError as e:
            logger.error(f"保存配置文件失败: {e}")
            raise ConfigError(f"无法保存配置文件: {e}") from e

    @classmethod
    def save_thresholds(cls) -> None:
        try:
            with open(settings.thresholds_file_path, "w", encoding="utf-8") as f:
                json.dump(cls._thresholds, f, indent=2, ensure_ascii=False)
            cls._last_thresholds_modified = os.path.getmtime(settings.thresholds_file_path)
            logger.info(f"阈值配置已保存: {settings.thresholds_file_path}")
        except IOError as e:
            logger.error(f"保存阈值配置失败: {e}")
            raise ConfigError(f"无法保存阈值配置文件: {e}") from e

    @classmethod
    def get(cls, key: str, default: Any = None, auto_reload: bool = True) -> Any:
        if auto_reload:
            cls.load_config()
        keys = key.split(".")
        value = cls._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    @classmethod
    def set(cls, key: str, value: Any) -> None:
        cls.load_config()
        keys = key.split(".")
        config = cls._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
        cls.save_config()

    @classmethod
    def get_threshold(cls, channel_id: Optional[int] = None, auto_reload: bool = True) -> Dict[str, Any]:
        if auto_reload:
            cls.load_thresholds()
        if channel_id is not None:
            channel_config = cls._thresholds.get("channels", {}).get(str(channel_id), {})
            if channel_config:
                return channel_config
        return cls._thresholds.get("global", cls._get_default_thresholds()["global"])

    @classmethod
    def set_threshold(cls, channel_id: Optional[int], threshold_config: Dict[str, Any]) -> None:
        cls.load_thresholds()
        if channel_id is None:
            cls._thresholds["global"] = threshold_config
        else:
            if "channels" not in cls._thresholds:
                cls._thresholds["channels"] = {}
            cls._thresholds["channels"][str(channel_id)] = threshold_config
        cls.save_thresholds()

    @classmethod
    def get_sensor_weights(cls) -> Dict[str, float]:
        return cls.get("sensor_weights", {"capacitive": 0.6, "ultrasonic": 0.4})

    @classmethod
    def set_sensor_weights(cls, capacitive: float, ultrasonic: float) -> None:
        if abs(capacitive + ultrasonic - 1.0) > 0.001:
            raise ValueError("传感器权重之和必须为1.0")
        cls.set("sensor_weights", {"capacitive": capacitive, "ultrasonic": ultrasonic})

    @classmethod
    def get_alarm_settings(cls) -> Dict[str, Any]:
        return cls.get("alarm_settings", {
            "consecutive_threshold": 3,
            "drift_detection_window": 5,
            "drift_rate_threshold": 0.1
        })

    @classmethod
    def get_sampling_settings(cls) -> Dict[str, Any]:
        return cls.get("sampling", {"frequency_ms": 100, "max_channels": 8})

    @classmethod
    def enable_auto_reload(cls) -> None:
        cls._auto_reload_enabled = True
        logger.info("配置自动重载已启用")

    @classmethod
    def disable_auto_reload(cls) -> None:
        cls._auto_reload_enabled = False
        logger.info("配置自动重载已禁用")

    @classmethod
    def reload_all(cls) -> None:
        cls.load_config(force_reload=True)
        cls.load_thresholds(force_reload=True)
        logger.info("所有配置已重新加载")

    @classmethod
    def get_config_info(cls) -> Dict[str, Any]:
        return {
            "config_file": settings.config_file_path,
            "thresholds_file": settings.thresholds_file_path,
            "config_last_modified": datetime.fromtimestamp(cls._last_config_modified).isoformat(),
            "thresholds_last_modified": datetime.fromtimestamp(cls._last_thresholds_modified).isoformat(),
            "auto_reload_enabled": cls._auto_reload_enabled
        }


AppConfig.load_config()
AppConfig.load_thresholds()
