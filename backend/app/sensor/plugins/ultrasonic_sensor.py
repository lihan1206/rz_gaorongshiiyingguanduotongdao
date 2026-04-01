"""
超声波液位传感器驱动
支持HC-SR04等超声波测距模块
"""

import logging
import re
from datetime import datetime
from typing import Optional

from app.sensor.sensor import SensorData, SerialConnectionError
from app.sensor.plugins import BaseSensorDriver, SensorCapabilities, register_sensor

logger = logging.getLogger(__name__)


@register_sensor("ultrasonic")
class UltrasonicSensorDriver(BaseSensorDriver):
    """
    超声波液位传感器驱动
    通过串口读取超声波测距数据，计算液位高度
    """

    def __init__(self, channel_id: int, config: dict):
        super().__init__(channel_id, config)
        self._port = config.get("port", f"/dev/ttyUSB{channel_id - 1}")
        self._baudrate = config.get("baudrate", 9600)
        self._timeout = config.get("timeout", 1.0)
        self._tank_height = config.get("tank_height", 200.0)  # 容器高度（cm）
        self._empty_distance = config.get("empty_distance", 200.0)  # 空罐时的距离（cm）
        self._serial = None
        self._capabilities = SensorCapabilities(
            supports_temperature=True,
            min_range=2.0,  # 超声波最小测量距离
            max_range=400.0,  # 超声波最大测量距离
            accuracy=0.3,
            response_time_ms=50,
        )

    @property
    def sensor_type(self) -> str:
        return "ultrasonic"

    def connect(self) -> None:
        """连接超声波传感器"""
        try:
            import serial
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                timeout=self._timeout,
            )
            self._connected = True
            logger.info(f"超声波传感器 {self.channel_id} 已连接到 {self._port}")
        except Exception as e:
            self._connected = False
            raise SerialConnectionError(f"连接超声波传感器失败: {e}") from e

    def disconnect(self) -> None:
        """断开超声波传感器"""
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._connected = False
        logger.info(f"超声波传感器 {self.channel_id} 已断开")

    def _distance_to_level(self, distance: float) -> float:
        """
        将距离转换为液位高度
        液位 = 容器高度 - (测量距离 - 传感器到罐顶距离)
        """
        level = self._tank_height - distance
        return max(0.0, min(self._tank_height, level))

    def _parse_data(self, raw_line: str) -> Optional[tuple[float, Optional[float]]]:
        """
        解析传感器数据
        支持格式:
        - JSON: {"distance": 123.45, "temp": 25.0}
        - CSV: distance,temp
        - 简单数值: 123.45
        """
        raw_line = raw_line.strip()

        try:
            # JSON格式
            if raw_line.startswith("{") and raw_line.endswith("}"):
                import json
                data = json.loads(raw_line)
                distance = float(data.get("distance", 0))
                temp = data.get("temp") or data.get("temperature")
                return distance, float(temp) if temp else None

            # CSV格式
            if "," in raw_line:
                parts = raw_line.split(",")
                distance = float(parts[0].strip())
                temp = float(parts[1].strip()) if len(parts) > 1 else None
                return distance, temp

            # 简单数值格式
            distance = float(raw_line)
            return distance, None

        except (ValueError, json.JSONDecodeError) as e:
            logger.warning(f"数据解析失败: {raw_line}, 错误: {e}")
            return None

    def read(self) -> Optional[SensorData]:
        """读取超声波传感器数据"""
        if not self._connected or not self._serial:
            return None

        try:
            import serial
            line = self._serial.readline()
            if not line:
                return None

            raw_data = line.decode("utf-8", errors="ignore").strip()
            parsed = self._parse_data(raw_data)

            if parsed is None:
                return None

            distance, temperature = parsed
            level = self._distance_to_level(distance)

            return SensorData(
                channel_id=self.channel_id,
                value=level,
                timestamp=datetime.utcnow(),
                temperature=temperature,
                raw_data=raw_data,
            )

        except serial.SerialException as e:
            logger.error(f"超声波传感器 {self.channel_id} 串口错误: {e}")
            self._connected = False
            raise SerialConnectionError(f"串口错误: {e}") from e
        except Exception as e:
            logger.error(f"超声波传感器 {self.channel_id} 读取失败: {e}")
            return None


@register_sensor("ultrasonic_hcsr04")
class HCSR04SensorDriver(UltrasonicSensorDriver):
    """
    HC-SR04 专用驱动
    针对HC-SR04模块优化的驱动
    """

    def __init__(self, channel_id: int, config: dict):
        super().__init__(channel_id, config)
        self._capabilities = SensorCapabilities(
            supports_temperature=False,
            min_range=2.0,
            max_range=400.0,
            accuracy=0.3,
            response_time_ms=60,
        )

    @property
    def sensor_type(self) -> str:
        return "ultrasonic_hcsr04"

    def read(self) -> Optional[SensorData]:
        """读取HC-SR04数据"""
        data = super().read()
        if data:
            # HC-SR04通常不提供温度数据
            data.temperature = None
        return data
