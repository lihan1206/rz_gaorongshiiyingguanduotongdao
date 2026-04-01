"""
电容式液位传感器驱动
支持电容式液位检测模块
"""

import logging
from datetime import datetime
from typing import Optional

from app.sensor.sensor import SensorData, SerialConnectionError
from app.sensor.plugins import BaseSensorDriver, SensorCapabilities, register_sensor

logger = logging.getLogger(__name__)


@register_sensor("capacitive")
class CapacitiveSensorDriver(BaseSensorDriver):
    """
    电容式液位传感器驱动
    通过串口或I2C读取电容传感器数据
    适用于各种液体，不受颜色、透明度影响
    """

    def __init__(self, channel_id: int, config: dict):
        super().__init__(channel_id, config)
        self._port = config.get("port", f"/dev/ttyUSB{channel_id - 1}")
        self._baudrate = config.get("baudrate", 9600)
        self._timeout = config.get("timeout", 1.0)
        self._tank_height = config.get("tank_height", 100.0)  # 容器高度
        self._probe_length = config.get("probe_length", 100.0)  # 探针长度
        self._empty_capacitance = config.get("empty_capacitance", 0.0)  # 空罐电容值
        self._full_capacitance = config.get("full_capacitance", 1000.0)  # 满罐电容值
        self._serial = None
        self._capabilities = SensorCapabilities(
            supports_temperature=True,
            min_range=0.0,
            max_range=100.0,
            accuracy=0.1,
            response_time_ms=100,
        )

    @property
    def sensor_type(self) -> str:
        return "capacitive"

    def connect(self) -> None:
        """连接电容式传感器"""
        try:
            import serial
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                timeout=self._timeout,
            )
            self._connected = True
            logger.info(f"电容式传感器 {self.channel_id} 已连接到 {self._port}")
        except Exception as e:
            self._connected = False
            raise SerialConnectionError(f"连接电容式传感器失败: {e}") from e

    def disconnect(self) -> None:
        """断开电容式传感器"""
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._connected = False
        logger.info(f"电容式传感器 {self.channel_id} 已断开")

    def _capacitance_to_level(self, capacitance: float) -> float:
        """
        将电容值转换为液位百分比
        """
        if self._full_capacitance <= self._empty_capacitance:
            return 0.0

        # 计算百分比
        percentage = (capacitance - self._empty_capacitance) / (
            self._full_capacitance - self._empty_capacitance
        )
        return max(0.0, min(100.0, percentage * 100))

    def _parse_data(self, raw_line: str) -> Optional[tuple[float, Optional[float]]]:
        """
        解析传感器数据
        支持格式:
        - JSON: {"capacitance": 500.5, "temp": 25.0, "level": 50.0}
        - CSV: capacitance,temp
        - 简单数值: 500.5 (电容值)
        """
        raw_line = raw_line.strip()

        try:
            # JSON格式
            if raw_line.startswith("{") and raw_line.endswith("}"):
                import json
                data = json.loads(raw_line)

                # 如果传感器直接返回液位值
                if "level" in data:
                    level = float(data["level"])
                    temp = data.get("temp") or data.get("temperature")
                    return level, float(temp) if temp else None

                # 否则转换电容值
                capacitance = float(data.get("capacitance", 0))
                temp = data.get("temp") or data.get("temperature")
                return self._capacitance_to_level(capacitance), float(temp) if temp else None

            # CSV格式
            if "," in raw_line:
                parts = raw_line.split(",")
                capacitance = float(parts[0].strip())
                temp = float(parts[1].strip()) if len(parts) > 1 else None
                return self._capacitance_to_level(capacitance), temp

            # 简单数值格式（假设为电容值或百分比）
            value = float(raw_line)
            # 如果值在0-100之间，假设为百分比
            if 0 <= value <= 100:
                return value, None
            # 否则作为电容值转换
            return self._capacitance_to_level(value), None

        except (ValueError, json.JSONDecodeError) as e:
            logger.warning(f"数据解析失败: {raw_line}, 错误: {e}")
            return None

    def read(self) -> Optional[SensorData]:
        """读取电容式传感器数据"""
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

            level, temperature = parsed

            return SensorData(
                channel_id=self.channel_id,
                value=level,
                timestamp=datetime.utcnow(),
                temperature=temperature,
                raw_data=raw_data,
            )

        except serial.SerialException as e:
            logger.error(f"电容式传感器 {self.channel_id} 串口错误: {e}")
            self._connected = False
            raise SerialConnectionError(f"串口错误: {e}") from e
        except Exception as e:
            logger.error(f"电容式传感器 {self.channel_id} 读取失败: {e}")
            return None


@register_sensor("capacitive_fdc1004")
class FDC1004SensorDriver(CapacitiveSensorDriver):
    """
    Texas Instruments FDC1004 电容数字转换器专用驱动
    高精度4通道电容测量
    """

    def __init__(self, channel_id: int, config: dict):
        super().__init__(channel_id, config)
        self._i2c_address = config.get("i2c_address", 0x50)
        self._sample_rate = config.get("sample_rate", 100)  # Hz
        self._capabilities = SensorCapabilities(
            supports_temperature=True,
            min_range=0.0,
            max_range=100.0,
            accuracy=0.01,  # FDC1004提供高精度
            response_time_ms=10,
        )

    @property
    def sensor_type(self) -> str:
        return "capacitive_fdc1004"

    def _parse_data(self, raw_line: str) -> Optional[tuple[float, Optional[float]]]:
        """
        FDC1004专用数据解析
        支持更高精度的电容值读取
        """
        raw_line = raw_line.strip()

        try:
            # JSON格式，FDC1004通常返回更详细的数据
            if raw_line.startswith("{") and raw_line.endswith("}"):
                import json
                data = json.loads(raw_line)

                # FDC1004返回的是fF (femtofarad)
                capacitance_ff = float(data.get("capacitance_ff", 0))
                # 转换为pF
                capacitance_pf = capacitance_ff / 1000.0

                temp = data.get("temp") or data.get("temperature")

                # 如果直接返回液位百分比
                if "level_percent" in data:
                    return float(data["level_percent"]), float(temp) if temp else None

                return self._capacitance_to_level(capacitance_pf), float(temp) if temp else None

            # 简单数值（假设为fF）
            capacitance_ff = float(raw_line)
            capacitance_pf = capacitance_ff / 1000.0
            return self._capacitance_to_level(capacitance_pf), None

        except (ValueError, json.JSONDecodeError) as e:
            logger.warning(f"FDC1004数据解析失败: {raw_line}, 错误: {e}")
            return None
