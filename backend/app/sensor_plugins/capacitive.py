import random
import time
from datetime import datetime
from typing import Dict, Any, Optional

from app.sensor_plugins.base import SensorPlugin, SensorReading


class CapacitiveSensor(SensorPlugin):
    """电容式液位传感器插件"""
    
    plugin_type: str = "capacitive"
    plugin_name: str = "Capacitive Level Sensor"
    plugin_description: str = "电容式液位传感器，支持多通道采集"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.channel_id = config.get("channel_id", 1) if config else 1
        self.base_value = config.get("base_value", 50.0) if config else 50.0
        self.noise_level = config.get("noise_level", 2.0) if config else 2.0
        self._drift_start = None
        self._drift_rate = 0.0

    def connect(self) -> bool:
        """模拟连接电容传感器"""
        self._is_connected = True
        return True

    def disconnect(self) -> None:
        """断开电容传感器连接"""
        self._is_connected = False

    def start_drift(self, rate: float = -0.1):
        """开始模拟漂移"""
        self._drift_start = time.time()
        self._drift_rate = rate

    def stop_drift(self):
        """停止模拟漂移"""
        self._drift_start = None

    def read(self) -> SensorReading:
        """读取电容传感器数据"""
        if not self._is_connected:
            raise ConnectionError("Capacitive sensor not connected")

        noise = random.uniform(-self.noise_level, self.noise_level)
        drift = 0.0
        if self._drift_start:
            drift = self._drift_rate * (time.time() - self._drift_start)
        
        value = max(0.0, min(100.0, self.base_value + noise + drift))
        
        return SensorReading(
            channel_id=self.channel_id,
            value=round(value, 3),
            timestamp=datetime.utcnow(),
            metadata={
                "sensor_type": "capacitive",
                "raw_value": value,
                "filtered_value": value
            }
        )
