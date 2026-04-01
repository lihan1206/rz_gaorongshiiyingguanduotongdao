import logging
from typing import Dict, List, Type, Optional, Any
from importlib import import_module
import os
import sys

from app.sensor_plugins.base import SensorPlugin, SensorReading

logger = logging.getLogger(__name__)


class PluginError(Exception):
    """插件相关错误基类"""
    pass


class PluginNotFoundError(PluginError):
    """插件未找到错误"""
    pass


class PluginLoadError(PluginError):
    """插件加载错误"""
    pass


class SensorPluginManager:
    """传感器插件管理器"""
    
    def __init__(self, plugin_package: str = "app.sensor_plugins"):
        self.plugin_package = plugin_package
        self._plugins: Dict[str, Type[SensorPlugin]] = {}
        self._instances: Dict[str, SensorPlugin] = {}
        self._discover_plugins()

    def _discover_plugins(self) -> None:
        """自动发现并加载可用的传感器插件"""
        try:
            package = import_module(self.plugin_package)
            package_path = os.path.dirname(package.__file__)
            
            for filename in os.listdir(package_path):
                if filename.endswith(".py") and filename not in ["__init__.py", "base.py", "manager.py"]:
                    module_name = f"{self.plugin_package}.{filename[:-3]}"
                    try:
                        module = import_module(module_name)
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if (
                                isinstance(attr, type)
                                and issubclass(attr, SensorPlugin)
                                and attr != SensorPlugin
                            ):
                                plugin_type = getattr(attr, "plugin_type", attr_name.lower())
                                self._plugins[plugin_type] = attr
                                logger.info(f"发现传感器插件: {plugin_type} -> {attr.plugin_name}")
                    except Exception as e:
                        logger.error(f"加载插件模块 {module_name} 失败: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"插件发现失败: {e}")
            raise PluginLoadError(f"无法发现插件: {e}") from e

    def get_plugin_class(self, plugin_type: str) -> Type[SensorPlugin]:
        """获取插件类"""
        if plugin_type not in self._plugins:
            raise PluginNotFoundError(f"未找到插件类型: {plugin_type}")
        return self._plugins[plugin_type]

    def create_plugin(
        self,
        plugin_type: str,
        instance_id: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> SensorPlugin:
        """创建插件实例"""
        plugin_class = self.get_plugin_class(plugin_type)
        
        try:
            instance = plugin_class(config)
            self._instances[instance_id] = instance
            logger.info(f"创建插件实例: {instance_id} ({plugin_type})")
            return instance
        except Exception as e:
            logger.error(f"创建插件实例 {instance_id} 失败: {e}")
            raise PluginLoadError(f"创建插件失败: {e}") from e

    def get_plugin(self, instance_id: str) -> Optional[SensorPlugin]:
        """获取插件实例"""
        return self._instances.get(instance_id)

    def remove_plugin(self, instance_id: str) -> bool:
        """移除插件实例"""
        if instance_id in self._instances:
            instance = self._instances[instance_id]
            if instance.is_connected():
                instance.disconnect()
            del self._instances[instance_id]
            logger.info(f"移除插件实例: {instance_id}")
            return True
        return False

    def list_available_plugins(self) -> List[Dict[str, Any]]:
        """列出所有可用的插件类型"""
        return [
            {
                "type": plugin_type,
                "name": plugin_class.plugin_name,
                "description": plugin_class.plugin_description,
            }
            for plugin_type, plugin_class in self._plugins.items()
        ]

    def list_active_instances(self) -> List[Dict[str, Any]]:
        """列出所有活动的插件实例"""
        return [
            {
                "instance_id": instance_id,
                "type": instance.plugin_type,
                "name": instance.plugin_name,
                "is_connected": instance.is_connected(),
            }
            for instance_id, instance in self._instances.items()
        ]

    def connect_all(self) -> None:
        """连接所有插件实例"""
        for instance_id, instance in self._instances.items():
            try:
                if not instance.is_connected():
                    instance.connect()
                    logger.info(f"插件 {instance_id} 已连接")
            except Exception as e:
                logger.error(f"连接插件 {instance_id} 失败: {e}")

    def disconnect_all(self) -> None:
        """断开所有插件实例的连接"""
        for instance_id, instance in self._instances.items():
            try:
                if instance.is_connected():
                    instance.disconnect()
                    logger.info(f"插件 {instance_id} 已断开连接")
            except Exception as e:
                logger.error(f"断开插件 {instance_id} 连接失败: {e}")

    def read_all(self) -> Dict[str, SensorReading]:
        """读取所有已连接插件的数据"""
        results: Dict[str, SensorReading] = {}
        for instance_id, instance in self._instances.items():
            try:
                if instance.is_connected():
                    results[instance_id] = instance.read()
            except Exception as e:
                logger.error(f"读取插件 {instance_id} 数据失败: {e}")
        return results
