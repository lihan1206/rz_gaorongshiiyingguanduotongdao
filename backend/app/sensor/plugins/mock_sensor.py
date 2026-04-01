"""
模拟传感器驱动
用于测试和演示
"""

import logging
import random
import math
from datetime import datetime
from typing import Optional

from app.sensor.sensor import SensorData
from app.sensor.plugins import BaseSensorDriver, SensorCapabilities, register_sensor

logger = logging.getLogger(__name__)


@register_sensor("mock")
class MockSensorDriver(BaseSensorDriver):
    """
    模拟传感器驱动
    生成模拟数据用于测试
    """

    def __init__(self, channel_id: int, config: dict):
        super().__init__(channel_id, config)
        self._base_value = config.get("base_value", 50.0)
        self._amplitude = config.get("amplitude", 10.0)
        self._noise_level = config.get("noise_level", 1.0)
        self._frequency = config.get("frequency", 0.1)  # Hz
        self._start_time = datetime.utcnow()
        self._capabilities = SensorCapabilities(
            supports_temperature=True,
            min_range=0.0,
            max_range=100.0,
            accuracy=0.1,
        )

    @property
    def sensor_type(self) -> str:
        return "mock"

    def connect(self) -> None:
        """连接模拟传感器"""
        self._connected = True
        logger.info(f"模拟传感器 {self.channel_id} 已连接")

    def disconnect(self) -> None:
        """断开模拟传感器"""
        self._connected = False
        logger.info(f"模拟传感器 {self.channel_id} 已断开")

    def read(self) -> Optional[SensorData]:
        """读取模拟数据"""
        if not self._connected:
            return None

        try:
            # 计算时间偏移
            now = datetime.utcnow()
            elapsed = (now - self._start_time).total_seconds()

            # 生成正弦波 + 噪声
            sine_value = math.sin(2 * math.pi * self._frequency * elapsed)
            value = self._base_value + self._amplitude * sine_value
            value += random.gauss(0, self._noise_level)

            # 限制范围
            value = max(0.0, min(100.0, value))

            # 生成温度数据
            temperature = 25.0 + random.gauss(0, 1.0)

            return SensorData(
                channel_id=self.channel_id,
                value=value,
                timestamp=now,
                temperature=temperature,
                raw_data=f"{{\"value\": {value:.2f}, \"temp\": {temperature:.2f}}}",
            )

        except Exception as e:
            logger.error(f"模拟传感器 {self.channel_id} 读取失败: {e}")
            return None


@register_sensor("random")
class RandomSensorDriver(BaseSensorDriver):
    """
    随机数据传感器驱动
    生成完全随机的数据
    """

    def __init__(self, channel_id: int, config: dict):
        super().__init__(channel_id, config)
        self._min_value = config.get("min_value", 0.0)
        self._max_value = config.get("max_value", 100.0)
        self._capabilities = SensorCapabilities(
            min_range=self._min_value,
            max_range=self._max_value,
            accuracy=0.1,
        )

    @property
    def sensor_type(self) -> str:
        return "random"

    def connect(self) -> None:
        self._connected = True
        logger.info(f"随机传感器 {self.channel_id} 已连接")

    def disconnect(self) -> None:
        self._connected = False
        logger.info(f"随机传感器 {self.channel_id} 已断开")

    def read(self) -> Optional[SensorData]:
        if not self._connected:
            return None

        value = random.uniform(self._min_value, self._max_value)
        return SensorData(
            channel_id=self.channel_id,
            value=value,
            timestamp=datetime.utcnow(),
            temperature=random.uniform(20.0, 30.0),
            raw_data=str(value),
        )


@register_sensor("step")
class StepSensorDriver(BaseSensorDriver):
    """
    阶梯变化传感器驱动
    模拟液位阶梯式变化
    """

    def __init__(self, channel_id: int, config: dict):
        super().__init__(channel_id, config)
        self._current_value = config.get("start_value", 50.0)
        self._step_size = config.get("step_size", 5.0)
        self._min_value = config.get("min_value", 0.0)
        self._max_value = config.get("max_value", 100.0)
        self._direction = 1  # 1 = 上升, -1 = 下降
        self._sample_count = 0
        self._samples_per_step = config.get("samples_per_step", 10)

    @property
    def sensor_type(self) -> str:
        return "step"

    def connect(self) -> None:
        self._connected = True
        logger.info(f"阶梯传感器 {self.channel_id} 已连接")

    def disconnect(self) -> None:
        self._connected = False
        logger.info(f"阶梯传感器 {self.channel_id} 已断开")

    def read(self) -> Optional[SensorData]:
        if not self._connected:
            return None

        self._sample_count += 1

        # 每N个样本改变一次
        if self._sample_count >= self._samples_per_step:
            self._sample_count = 0
            self._current_value += self._step_size * self._direction

            # 边界检查和方向反转
            if self._current_value >= self._max_value:
                self._current_value = self._max_value
                self._direction = -1
            elif self._current_value <= self._min_value:
                self._current_value = self._min_value
                self._direction = 1

        return SensorData(
            channel_id=self.channel_id,
            value=self._current_value,
            timestamp=datetime.utcnow(),
            temperature=25.0,
            raw_data=str(self._current_value),
        )
