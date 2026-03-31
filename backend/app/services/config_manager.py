import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "sampling_interval_ms": 100,
    "alarm_consecutive_count": 3,
    "drift_detection": {
        "enabled": True,
        "window_seconds": 5,
        "threshold_mm": 0.5,
    },
    "default_thresholds": {
        "warning_low": 50.0,
        "warning_high": 500.0,
        "alarm_type": "high",
    },
    "sensor_fusion": {
        "default_weight_a": 0.5,
        "default_weight_b": 0.5,
    },
}


class ConfigManager:
    _instance: Optional["ConfigManager"] = None
    _lock = threading.Lock()

    def __new__(cls, config_path: Optional[Path] = None) -> "ConfigManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path: Optional[Path] = None):
        if self._initialized:
            return

        self._config_path = config_path or Path(__file__).parent.parent / "core" / "config.json"
        self._config: Dict[str, Any] = {}
        self._last_modified: Optional[float] = None
        self._callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._config_lock = threading.RLock()
        self._initialized = True
        self._load_config()

    def _load_config(self) -> None:
        with self._config_lock:
            try:
                if not self._config_path.exists():
                    logger.warning(f"配置文件不存在: {self._config_path}, 使用默认配置")
                    self._config = DEFAULT_CONFIG.copy()
                    self._save_config()
                    return

                with open(self._config_path, "r", encoding="utf-8") as f:
                    self._config = json.load(f)

                self._last_modified = self._config_path.stat().st_mtime
                logger.info(f"配置加载成功: {self._config_path}")

            except json.JSONDecodeError as e:
                logger.error(f"配置文件JSON解析错误: {e}")
                self._config = DEFAULT_CONFIG.copy()
            except PermissionError as e:
                logger.error(f"配置文件权限错误: {e}")
                self._config = DEFAULT_CONFIG.copy()
            except Exception as e:
                logger.error(f"加载配置文件失败: {e}")
                self._config = DEFAULT_CONFIG.copy()

    def _save_config(self) -> None:
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=4, ensure_ascii=False)
            self._last_modified = self._config_path.stat().st_mtime
            logger.info(f"配置保存成功: {self._config_path}")
        except PermissionError as e:
            logger.error(f"保存配置文件权限错误: {e}")
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")

    def reload_if_changed(self) -> bool:
        with self._config_lock:
            try:
                if not self._config_path.exists():
                    return False

                current_mtime = self._config_path.stat().st_mtime
                if self._last_modified is None or current_mtime > self._last_modified:
                    old_config = self._config.copy()
                    self._load_config()
                    if old_config != self._config:
                        self._notify_callbacks()
                        return True
            except Exception as e:
                logger.error(f"检查配置文件变更失败: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        with self._config_lock:
            keys = key.split(".")
            value = self._config
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            return value

    def set(self, key: str, value: Any, auto_save: bool = True) -> None:
        with self._config_lock:
            keys = key.split(".")
            config = self._config
            for k in keys[:-1]:
                if k not in config:
                    config[k] = {}
                config = config[k]
            config[keys[-1]] = value

            if auto_save:
                self._save_config()
                self._notify_callbacks()

    def get_all(self) -> Dict[str, Any]:
        with self._config_lock:
            return self._config.copy()

    def update(self, updates: Dict[str, Any], auto_save: bool = True) -> None:
        with self._config_lock:
            self._deep_update(self._config, updates)
            if auto_save:
                self._save_config()
                self._notify_callbacks()

    def _deep_update(self, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._deep_update(target[key], value)
            else:
                target[key] = value

    def register_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _notify_callbacks(self) -> None:
        config_copy = self.get_all()
        for callback in self._callbacks:
            try:
                callback(config_copy)
            except Exception as e:
                logger.error(f"配置变更回调执行失败: {e}")

    @property
    def alarm_consecutive_count(self) -> int:
        return self.get("alarm_consecutive_count", 3)

    @property
    def drift_detection_enabled(self) -> bool:
        return self.get("drift_detection.enabled", True)

    @property
    def drift_window_seconds(self) -> int:
        return self.get("drift_detection.window_seconds", 5)

    @property
    def drift_threshold_mm(self) -> float:
        return self.get("drift_detection.threshold_mm", 0.5)

    @property
    def sampling_interval_ms(self) -> int:
        return self.get("sampling_interval_ms", 100)


config_manager = ConfigManager()


def get_config() -> ConfigManager:
    return config_manager


def load_config() -> Dict[str, Any]:
    return config_manager.get_all()
