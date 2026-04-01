"""
传感器插件系统
支持插件化扩展不同类型的传感器驱动
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from app.sensor.sensor import SensorData

logger = logging.getLogger(__name__)


@dataclass
class SensorCapabilities:
    """传感器能力描述"""
    supports_temperature: bool = False
    supports_pressure: bool = False
    supports_humidity: bool = False
    min_range: float = 0.0
    max_range: float = 100.0
    accuracy: float = 0.1
    response_time_ms: int = 100


class BaseSensorDriver(ABC):
    """
    传感器驱动基类
    所有传感器驱动必须继承此类
    """

    def __init__(self, channel_id: int, config: dict[str, Any]):
        self.channel_id = channel_id
        self.config = config
        self._connected = False
        self._capabilities = SensorCapabilities()

    @property
    def name(self) -> str:
        """驱动名称"""
        return self.__class__.__name__

    @property
    def sensor_type(self) -> str:
        """传感器类型标识"""
        return "base"

    @property
    def capabilities(self) -> SensorCapabilities:
        """获取传感器能力"""
        return self._capabilities

    @abstractmethod
    def connect(self) -> None:
        """连接传感器"""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """断开传感器连接"""
        pass

    @abstractmethod
    def read(self) -> Optional[SensorData]:
        """
        读取传感器数据
        Returns:
            SensorData: 传感器数据，读取失败返回None
        """
        pass

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._connected

    def health_check(self) -> bool:
        """健康检查"""
        return self._connected


class SensorPluginRegistry:
    """传感器插件注册表"""

    _drivers: dict[str, type[BaseSensorDriver]] = {}

    @classmethod
    def register(cls, sensor_type: str, driver_class: type[BaseSensorDriver]) -> None:
        """注册传感器驱动"""
        cls._drivers[sensor_type] = driver_class
        logger.info(f"传感器驱动已注册: {sensor_type} -> {driver_class.__name__}")

    @classmethod
    def unregister(cls, sensor_type: str) -> None:
        """注销传感器驱动"""
        if sensor_type in cls._drivers:
            del cls._drivers[sensor_type]
            logger.info(f"传感器驱动已注销: {sensor_type}")

    @classmethod
    def get_driver(cls, sensor_type: str) -> Optional[type[BaseSensorDriver]]:
        """获取传感器驱动类"""
        return cls._drivers.get(sensor_type)

    @classmethod
    def list_drivers(cls) -> list[str]:
        """列出所有已注册的驱动类型"""
        return list(cls._drivers.keys())

    @classmethod
    def create_driver(
        cls,
        sensor_type: str,
        channel_id: int,
        config: dict[str, Any],
    ) -> Optional[BaseSensorDriver]:
        """创建传感器驱动实例"""
        driver_class = cls.get_driver(sensor_type)
        if driver_class:
            return driver_class(channel_id, config)
        logger.error(f"未找到传感器驱动: {sensor_type}")
        return None


def register_sensor(sensor_type: str):
    """传感器驱动装饰器"""
    def decorator(driver_class: type[BaseSensorDriver]):
        SensorPluginRegistry.register(sensor_type, driver_class)
        return driver_class
    return decorator
