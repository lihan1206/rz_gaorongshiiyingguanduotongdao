import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ThresholdConfig:
    """阈值配置"""
    channel_id: int
    warning_low: float = 0.0
    warning_high: float = 100.0
    critical_low: float = -10.0
    critical_high: float = 110.0
    range_min: float = 0.0
    range_max: float = 100.0
    alarm_enabled: bool = True
    calibration_offset: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ThresholdConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class SensorConfig:
    """传感器配置"""
    channel_id: int
    port: str = "COM1"
    baudrate: int = 9600
    sensor_type: str = "capacitive"
    enabled: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SensorConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class SystemConfig:
    """系统配置"""
    sample_interval: float = 1.0
    fusion_algorithm: str = "average"
    alarm_cooldown_seconds: int = 60
    data_retention_days: int = 30
    log_level: str = "INFO"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SystemConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ConfigManager:
    """配置管理器 - 支持热更新配置"""

    def __init__(
        self,
        config_dir: Optional[str] = None,
        auto_reload: bool = True,
        reload_interval: float = 5.0,
    ):
        if config_dir is None:
            config_dir = os.path.join(os.path.dirname(__file__), "..", "..", "config")

        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.thresholds_file = self.config_dir / "thresholds.json"
        self.sensors_file = self.config_dir / "sensors.json"
        self.system_file = self.config_dir / "system.json"

        self._thresholds: dict[int, ThresholdConfig] = {}
        self._sensors: dict[int, SensorConfig] = {}
        self._system: SystemConfig = SystemConfig()

        self._callbacks: list[Callable[[str, Any], None]] = []
        self._lock = threading.RLock()
        self._auto_reload = auto_reload
        self._reload_interval = reload_interval
        self._stop_event = threading.Event()
        self._reload_thread: Optional[threading.Thread] = None
        self._file_mtimes: dict[str, float] = {}

        # 初始化配置文件
        self._init_config_files()

        # 加载配置
        self.load_all()

        # 启动自动重载线程
        if self._auto_reload:
            self._start_reload_thread()

    def _init_config_files(self) -> None:
        """初始化配置文件"""
        # thresholds.json
        if not self.thresholds_file.exists():
            default_thresholds = {
                "thresholds": [
                    {
                        "channel_id": 1,
                        "warning_low": 10.0,
                        "warning_high": 90.0,
                        "critical_low": 5.0,
                        "critical_high": 95.0,
                        "range_min": 0.0,
                        "range_max": 100.0,
                        "alarm_enabled": True,
                        "calibration_offset": 0.0,
                    }
                ]
            }
            self._save_json(self.thresholds_file, default_thresholds)
            logger.info(f"创建默认阈值配置文件: {self.thresholds_file}")

        # sensors.json
        if not self.sensors_file.exists():
            default_sensors = {
                "sensors": [
                    {
                        "channel_id": 1,
                        "port": "COM1",
                        "baudrate": 9600,
                        "sensor_type": "capacitive",
                        "enabled": True,
                    }
                ]
            }
            self._save_json(self.sensors_file, default_sensors)
            logger.info(f"创建默认传感器配置文件: {self.sensors_file}")

        # system.json
        if not self.system_file.exists():
            default_system = {
                "sample_interval": 1.0,
                "fusion_algorithm": "average",
                "alarm_cooldown_seconds": 60,
                "data_retention_days": 30,
                "log_level": "INFO",
            }
            self._save_json(self.system_file, default_system)
            logger.info(f"创建默认系统配置文件: {self.system_file}")

    def _save_json(self, filepath: Path, data: dict) -> None:
        """保存JSON文件"""
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存配置文件失败 {filepath}: {e}")
            raise

    def _load_json(self, filepath: Path) -> Optional[dict]:
        """加载JSON文件"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误 {filepath}: {e}")
            return None
        except FileNotFoundError:
            logger.warning(f"配置文件不存在: {filepath}")
            return None
        except Exception as e:
            logger.error(f"加载配置文件失败 {filepath}: {e}")
            return None

    def _get_file_mtime(self, filepath: Path) -> float:
        """获取文件修改时间"""
        try:
            return os.path.getmtime(filepath)
        except OSError:
            return 0.0

    def _check_and_reload(self) -> None:
        """检查并重新加载配置"""
        files_to_check = {
            "thresholds": self.thresholds_file,
            "sensors": self.sensors_file,
            "system": self.system_file,
        }

        for config_name, filepath in files_to_check.items():
            current_mtime = self._get_file_mtime(filepath)
            last_mtime = self._file_mtimes.get(str(filepath), 0)

            if current_mtime > last_mtime:
                logger.info(f"检测到配置文件变更: {filepath}")
                self._file_mtimes[str(filepath)] = current_mtime

                if config_name == "thresholds":
                    self._load_thresholds()
                elif config_name == "sensors":
                    self._load_sensors()
                elif config_name == "system":
                    self._load_system()

                self._notify_callbacks(config_name, self.get_config(config_name))

    def _reload_loop(self) -> None:
        """配置重载循环"""
        while not self._stop_event.is_set():
            try:
                self._check_and_reload()
            except Exception as e:
                logger.error(f"配置重载出错: {e}")
            time.sleep(self._reload_interval)

    def _start_reload_thread(self) -> None:
        """启动配置重载线程"""
        if self._reload_thread is None or not self._reload_thread.is_alive():
            self._stop_event.clear()
            self._reload_thread = threading.Thread(
                target=self._reload_loop,
                name="ConfigReloadThread",
                daemon=True,
            )
            self._reload_thread.start()
            logger.info("配置热更新线程已启动")

    def stop_reload_thread(self) -> None:
        """停止配置重载线程"""
        self._stop_event.set()
        if self._reload_thread and self._reload_thread.is_alive():
            self._reload_thread.join(timeout=2.0)
            logger.info("配置热更新线程已停止")

    def _load_thresholds(self) -> None:
        """加载阈值配置"""
        data = self._load_json(self.thresholds_file)
        if data and "thresholds" in data:
            with self._lock:
                self._thresholds = {}
                for item in data["thresholds"]:
                    try:
                        config = ThresholdConfig.from_dict(item)
                        self._thresholds[config.channel_id] = config
                    except Exception as e:
                        logger.error(f"解析阈值配置失败: {item}, 错误: {e}")
            logger.debug(f"已加载 {len(self._thresholds)} 个阈值配置")

    def _load_sensors(self) -> None:
        """加载传感器配置"""
        data = self._load_json(self.sensors_file)
        if data and "sensors" in data:
            with self._lock:
                self._sensors = {}
                for item in data["sensors"]:
                    try:
                        config = SensorConfig.from_dict(item)
                        self._sensors[config.channel_id] = config
                    except Exception as e:
                        logger.error(f"解析传感器配置失败: {item}, 错误: {e}")
            logger.debug(f"已加载 {len(self._sensors)} 个传感器配置")

    def _load_system(self) -> None:
        """加载系统配置"""
        data = self._load_json(self.system_file)
        if data:
            with self._lock:
                try:
                    self._system = SystemConfig.from_dict(data)
                except Exception as e:
                    logger.error(f"解析系统配置失败: {e}")
            logger.debug("已加载系统配置")

    def load_all(self) -> None:
        """加载所有配置"""
        self._load_thresholds()
        self._load_sensors()
        self._load_system()

        # 更新文件修改时间
        self._file_mtimes[str(self.thresholds_file)] = self._get_file_mtime(self.thresholds_file)
        self._file_mtimes[str(self.sensors_file)] = self._get_file_mtime(self.sensors_file)
        self._file_mtimes[str(self.system_file)] = self._get_file_mtime(self.system_file)

        logger.info("所有配置已加载")

    def save_thresholds(self) -> None:
        """保存阈值配置"""
        with self._lock:
            data = {
                "thresholds": [config.to_dict() for config in self._thresholds.values()]
            }
        self._save_json(self.thresholds_file, data)
        self._file_mtimes[str(self.thresholds_file)] = self._get_file_mtime(self.thresholds_file)
        logger.info("阈值配置已保存")

    def save_sensors(self) -> None:
        """保存传感器配置"""
        with self._lock:
            data = {
                "sensors": [config.to_dict() for config in self._sensors.values()]
            }
        self._save_json(self.sensors_file, data)
        self._file_mtimes[str(self.sensors_file)] = self._get_file_mtime(self.sensors_file)
        logger.info("传感器配置已保存")

    def save_system(self) -> None:
        """保存系统配置"""
        with self._lock:
            data = self._system.to_dict()
        self._save_json(self.system_file, data)
        self._file_mtimes[str(self.system_file)] = self._get_file_mtime(self.system_file)
        logger.info("系统配置已保存")

    def get_threshold(self, channel_id: int) -> Optional[ThresholdConfig]:
        """获取通道阈值配置"""
        with self._lock:
            return self._thresholds.get(channel_id)

    def set_threshold(self, config: ThresholdConfig) -> None:
        """设置通道阈值配置"""
        with self._lock:
            self._thresholds[config.channel_id] = config
        self.save_thresholds()

    def get_sensor(self, channel_id: int) -> Optional[SensorConfig]:
        """获取传感器配置"""
        with self._lock:
            return self._sensors.get(channel_id)

    def set_sensor(self, config: SensorConfig) -> None:
        """设置传感器配置"""
        with self._lock:
            self._sensors[config.channel_id] = config
        self.save_sensors()

    def get_system(self) -> SystemConfig:
        """获取系统配置"""
        with self._lock:
            return self._system

    def set_system(self, config: SystemConfig) -> None:
        """设置系统配置"""
        with self._lock:
            self._system = config
        self.save_system()

    def get_config(self, config_type: str) -> Any:
        """获取配置"""
        with self._lock:
            if config_type == "thresholds":
                return {k: v.to_dict() for k, v in self._thresholds.items()}
            elif config_type == "sensors":
                return {k: v.to_dict() for k, v in self._sensors.items()}
            elif config_type == "system":
                return self._system.to_dict()
        return None

    def add_callback(self, callback: Callable[[str, Any], None]) -> None:
        """添加配置变更回调"""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[str, Any], None]) -> None:
        """移除配置变更回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _notify_callbacks(self, config_type: str, config_data: Any) -> None:
        """通知配置变更"""
        for callback in self._callbacks:
            try:
                callback(config_type, config_data)
            except Exception as e:
                logger.error(f"配置变更回调执行失败: {e}")


# 全局配置管理器实例
config_manager = ConfigManager()
