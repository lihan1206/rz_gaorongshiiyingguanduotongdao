from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass


@dataclass
class SensorReading:
    """传感器读数基类"""
    channel_id: int
    value: float
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None
    temperature: Optional[float] = None


class SensorPlugin(ABC):
    """传感器插件基类 - 所有传感器插件必须继承此类"""
    
    plugin_type: str = "base"
    plugin_name: str = "Base Sensor Plugin"
    plugin_description: str = "Base class for all sensor plugins"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._is_connected: bool = False

    @abstractmethod
    def connect(self) -> bool:
        """连接传感器"""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """断开传感器连接"""
        pass

    @abstractmethod
    def read(self) -> SensorReading:
        """读取传感器数据"""
        pass

    def is_connected(self) -> bool:
        """检查传感器是否连接"""
        return self._is_connected

    def get_info(self) -> Dict[str, Any]:
        """获取插件信息"""
        return {
            "type": self.plugin_type,
            "name": self.plugin_name,
            "description": self.plugin_description,
            "config": self.config,
            "is_connected": self._is_connected,
        }
