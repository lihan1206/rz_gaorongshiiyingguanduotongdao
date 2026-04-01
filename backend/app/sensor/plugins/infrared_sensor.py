"""
红外液位传感器驱动
支持红外测距传感器
"""

import logging
from datetime import datetime
from typing import Optional

from app.sensor.sensor import SensorData, SerialConnectionError
from app.sensor.plugins import BaseSensorDriver, SensorCapabilities, register_sensor

logger = logging.getLogger(__name__)


@register_sensor("infrared")
class InfraredSensorDriver(BaseSensorDriver):
    """
    红外液位传感器驱动
    通过串口或ADC读取红外传感器数据
    """

    def __init__(self, channel_id: int, config: dict):
        super().__init__(channel_id, config)
        self._port = config.get("port", f"/dev/ttyUSB{channel_id - 1}")
        self._baudrate = config.get("baudrate", 9600)
        self._timeout = config.get("timeout", 1.0)
        self._tank_height = config.get("tank_height", 100.0)
        self._adc_resolution = config.get("adc_resolution", 4096)  # 12位ADC
        self._voltage_ref = config.get("voltage_ref", 3.3)
        self._serial = None
        self._capabilities = SensorCapabilities(
            supports_temperature=False,
            min_range=10.0,
            max_range=80.0,  # 红外传感器通常测量范围较小
            accuracy=0.5,
            response_time_ms=30,
        )

    @property
    def sensor_type(self) -> str:
        return "infrared"

    def connect(self) -> None:
        """连接红外传感器"""
        try:
            import serial
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                timeout=self._timeout,
            )
            self._connected = True
            logger.info(f"红外传感器 {self.channel_id} 已连接到 {self._port}")
        except Exception as e:
            self._connected = False
            raise SerialConnectionError(f"连接红外传感器失败: {e}") from e

    def disconnect(self) -> None:
        """断开红外传感器"""
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._connected = False
        logger.info(f"红外传感器 {self.channel_id} 已断开")

    def _adc_to_distance(self, adc_value: int) -> float:
        """
        将ADC值转换为距离
        红外传感器通常输出与距离成反比的电压
        """
        # 简化的转换公式，实际应根据传感器校准曲线调整
        voltage = (adc_value / self._adc_resolution) * self._voltage_ref
        # 假设距离与电压成反比关系
        if voltage > 0.1:  # 避免除零
            distance = 27.86 / (voltage - 0.1)  # GP2Y0A21YK0F近似公式
            return min(80.0, max(10.0, distance))
        return 80.0

    def _parse_data(self, raw_line: str) -> Optional[float]:
        """解析传感器数据"""
        raw_line = raw_line.strip()

        try:
            # JSON格式
            if raw_line.startswith("{") and raw_line.endswith("}"):
                import json
                data = json.loads(raw_line)
                if "adc" in data:
                    return self._adc_to_distance(int(data["adc"]))
                if "distance" in data:
                    return float(data["distance"])
                if "voltage" in data:
                    voltage = float(data["voltage"])
                    adc_value = int((voltage / self._voltage_ref) * self._adc_resolution)
                    return self._adc_to_distance(adc_value)

            # 简单数值（假设为ADC值）
            adc_value = int(raw_line)
            return self._adc_to_distance(adc_value)

        except (ValueError, json.JSONDecodeError) as e:
            logger.warning(f"数据解析失败: {raw_line}, 错误: {e}")
            return None

    def read(self) -> Optional[SensorData]:
        """读取红外传感器数据"""
        if not self._connected or not self._serial:
            return None

        try:
            import serial
            line = self._serial.readline()
            if not line:
                return None

            raw_data = line.decode("utf-8", errors="ignore").strip()
            distance = self._parse_data(raw_data)

            if distance is None:
                return None

            # 转换为液位高度
            level = max(0.0, min(self._tank_height, self._tank_height - distance))

            return SensorData(
                channel_id=self.channel_id,
                value=level,
                timestamp=datetime.utcnow(),
                temperature=None,
                raw_data=raw_data,
            )

        except serial.SerialException as e:
            logger.error(f"红外传感器 {self.channel_id} 串口错误: {e}")
            self._connected = False
            raise SerialConnectionError(f"串口错误: {e}") from e
        except Exception as e:
            logger.error(f"红外传感器 {self.channel_id} 读取失败: {e}")
            return None


@register_sensor("infrared_sharp")
class SharpInfraredDriver(InfraredSensorDriver):
    """
    Sharp红外传感器专用驱动
    针对Sharp GP2Y0A系列传感器优化
    """

    def __init__(self, channel_id: int, config: dict):
        super().__init__(channel_id, config)
        self._model = config.get("model", "GP2Y0A21YK0F")
        self._capabilities = SensorCapabilities(
            supports_temperature=False,
            min_range=10.0,
            max_range=80.0,
            accuracy=0.5,
            response_time_ms=38,  # GP2Y0A21YK0F典型响应时间
        )

    @property
    def sensor_type(self) -> str:
        return "infrared_sharp"

    def _adc_to_distance(self, adc_value: int) -> float:
        """
        Sharp传感器专用距离转换
        基于传感器数据手册的校准曲线
        """
        voltage = (adc_value / self._adc_resolution) * self._voltage_ref

        # 根据型号选择转换公式
        if self._model == "GP2Y0A02YK0F":  # 20-150cm
            if voltage > 0.4:
                distance = 60.0 / (voltage - 0.1)
            else:
                distance = 150.0
        elif self._model == "GP2Y0A21YK0F":  # 10-80cm
            if voltage > 0.4:
                distance = 27.86 / (voltage - 0.1)
            else:
                distance = 80.0
        elif self._model == "GP2Y0A41SK0F":  # 4-30cm
            if voltage > 0.4:
                distance = 12.0 / (voltage - 0.1)
            else:
                distance = 30.0
        else:
            # 默认公式
            if voltage > 0.4:
                distance = 27.86 / (voltage - 0.1)
            else:
                distance = 80.0

        return min(self._capabilities.max_range, max(self._capabilities.min_range, distance))
