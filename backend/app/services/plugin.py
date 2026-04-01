import importlib
import inspect
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

from app.services.sensor import BaseSensor, SensorReading, SensorType

logger = logging.getLogger(__name__)


class PluginType(str, Enum):
    sensor = "sensor"
    fusion = "fusion"
    alarm = "alarm"
    storage = "storage"
    api = "api"


@dataclass
class PluginInfo:
    name: str
    version: str
    plugin_type: PluginType
    description: str
    author: Optional[str] = None
    enabled: bool = True


class BasePlugin(ABC):
    @property
    @abstractmethod
    def info(self) -> PluginInfo:
        pass

    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def shutdown(self) -> None:
        pass


class SensorPlugin(BasePlugin):
    @abstractmethod
    def create_sensor(
        self,
        channel_id: int,
        sensor_type: SensorType,
        **kwargs,
    ) -> BaseSensor:
        pass


class FusionPlugin(BasePlugin):
    @abstractmethod
    def fuse(
        self,
        value_a: Optional[float],
        value_b: Optional[float],
        **kwargs,
    ) -> float:
        pass


class AlarmPlugin(BasePlugin):
    @abstractmethod
    def check_alarm(
        self,
        channel_id: int,
        value: float,
        threshold: float,
        **kwargs,
    ) -> bool:
        pass


class PluginManager:
    def __init__(self, plugin_dir: Optional[Path] = None):
        self.plugin_dir = plugin_dir or Path(__file__).parent / "plugins"
        self._plugins: Dict[str, BasePlugin] = {}
        self._sensor_plugins: Dict[str, SensorPlugin] = {}
        self._fusion_plugins: Dict[str, FusionPlugin] = {}
        self._alarm_plugins: Dict[str, AlarmPlugin] = {}
        self._configs: Dict[str, Dict[str, Any]] = {}

    def discover_plugins(self) -> List[str]:
        discovered = []
        if not self.plugin_dir.exists():
            logger.warning(f"插件目录不存在: {self.plugin_dir}")
            return discovered

        for plugin_path in self.plugin_dir.glob("*.py"):
            if plugin_path.name.startswith("_"):
                continue

            module_name = plugin_path.stem
            try:
                spec = importlib.util.spec_from_file_location(
                    f"plugins.{module_name}",
                    plugin_path,
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    for name, obj in inspect.getmembers(module):
                        if (
                            inspect.isclass(obj)
                            and issubclass(obj, BasePlugin)
                            and obj != BasePlugin
                            and obj != SensorPlugin
                            and obj != FusionPlugin
                            and obj != AlarmPlugin
                        ):
                            discovered.append(f"{module_name}.{name}")
                            logger.info(f"发现插件: {module_name}.{name}")

            except Exception as e:
                logger.error(f"加载插件文件失败 {plugin_path}: {e}")

        return discovered

    def register_plugin(
        self,
        plugin: BasePlugin,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        info = plugin.info
        if info.name in self._plugins:
            logger.warning(f"插件已存在，将覆盖: {info.name}")

        try:
            plugin.initialize(config or {})
            self._plugins[info.name] = plugin
            self._configs[info.name] = config or {}

            if isinstance(plugin, SensorPlugin):
                self._sensor_plugins[info.name] = plugin
            if isinstance(plugin, FusionPlugin):
                self._fusion_plugins[info.name] = plugin
            if isinstance(plugin, AlarmPlugin):
                self._alarm_plugins[info.name] = plugin

            logger.info(f"插件注册成功: {info.name} v{info.version}")
        except Exception as e:
            logger.error(f"插件初始化失败 {info.name}: {e}")

    def unregister_plugin(self, name: str) -> None:
        if name not in self._plugins:
            logger.warning(f"插件不存在: {name}")
            return

        try:
            plugin = self._plugins[name]
            plugin.shutdown()

            if name in self._sensor_plugins:
                del self._sensor_plugins[name]
            if name in self._fusion_plugins:
                del self._fusion_plugins[name]
            if name in self._alarm_plugins:
                del self._alarm_plugins[name]

            del self._plugins[name]
            del self._configs[name]

            logger.info(f"插件已注销: {name}")
        except Exception as e:
            logger.error(f"插件关闭失败 {name}: {e}")

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        return self._plugins.get(name)

    def get_sensor_plugin(self, name: str) -> Optional[SensorPlugin]:
        return self._sensor_plugins.get(name)

    def get_fusion_plugin(self, name: str) -> Optional[FusionPlugin]:
        return self._fusion_plugins.get(name)

    def get_alarm_plugin(self, name: str) -> Optional[AlarmPlugin]:
        return self._alarm_plugins.get(name)

    def list_plugins(self) -> List[PluginInfo]:
        return [plugin.info for plugin in self._plugins.values()]

    def update_plugin_config(self, name: str, config: Dict[str, Any]) -> None:
        if name not in self._plugins:
            logger.warning(f"插件不存在: {name}")
            return

        plugin = self._plugins[name]
        try:
            plugin.shutdown()
            plugin.initialize(config)
            self._configs[name] = config
            logger.info(f"插件配置已更新: {name}")
        except Exception as e:
            logger.error(f"插件配置更新失败 {name}: {e}")

    def shutdown_all(self) -> None:
        for name in list(self._plugins.keys()):
            try:
                self.unregister_plugin(name)
            except Exception as e:
                logger.error(f"关闭插件失败 {name}: {e}")


_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager
