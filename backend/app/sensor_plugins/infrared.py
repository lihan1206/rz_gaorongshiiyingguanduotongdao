import random
import time
from datetime import datetime
from typing import Dict, Any, Optional

from app.sensor_plugins.base import SensorPlugin, SensorReading


class InfraredSensor(SensorPlugin):
    """红外液位传感器插件"""
    
    plugin_type: str = "infrared"
    plugin_name: str = "Infrared Level Sensor"
    plugin_description: str = "红外液位传感器，支持非接触式测量"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.channel_id = config.get("channel_id", 1) if config else 1
        self.base_value = config.get("base_value", 50.0) if config else 50.0
        self.noise_level = config.get("noise_level", 1.5) if config else 1.5
        self._drift_start = None
        self._drift_rate = 0.0

    def connect(self) -> bool:
        """模拟连接红外传感器"""
        self._is_connected = True
        return True

    def disconnect(self) -> None:
        """断开红外传感器连接"""
        self._is_connected = False

    def start_drift(self, rate: float = -0.1):
        """开始模拟漂移"""
        self._drift_start = time.time()
        self._drift_rate = rate

    def stop_drift(self):
        """停止模拟漂移"""
        self._drift_start = None

    def read(self) -> SensorReading:
        """读取红外传感器数据"""
        if not self._is_connected:
            raise ConnectionError("Infrared sensor not connected")

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
                "sensor_type": "infrared",
                "raw_value": value,
                "filtered_value": value,
                "light_intensity": random.uniform(0, 100)
            }
        )
