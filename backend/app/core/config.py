import json
from typing import Dict, Any
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "高融石英管多通道液位同步检测系统"
    db_host: str = "db"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = "root"
    db_name: str = "quartz_monitor"
    cors_origins: str = "*"
    config_file_path: str = "config.json"

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
    _last_modified: float = 0

    @classmethod
    def load_config(cls) -> None:
        try:
            with open(settings.config_file_path, "r", encoding="utf-8") as f:
                cls._config = json.load(f)
        except FileNotFoundError:
            cls._config = cls._get_default_config()
            cls.save_config()

    @classmethod
    def _get_default_config(cls) -> Dict[str, Any]:
        return {
            "sensor_weights": {"capacitive": 0.6, "ultrasonic": 0.4},
            "default_thresholds": {
                "warning_low": 10.0,
                "warning_high": 90.0,
                "drift_threshold": 0.5,
                "drift_time_window": 5
            },
            "alarm_settings": {
                "consecutive_threshold": 3,
                "drift_detection_window": 5,
                "drift_rate_threshold": 0.1
            },
            "sampling": {"frequency_ms": 100, "max_channels": 8}
        }

    @classmethod
    def save_config(cls) -> None:
        with open(settings.config_file_path, "w", encoding="utf-8") as f:
            json.dump(cls._config, f, indent=2, ensure_ascii=False)

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
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
        keys = key.split(".")
        config = cls._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
        cls.save_config()

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


AppConfig.load_config()
