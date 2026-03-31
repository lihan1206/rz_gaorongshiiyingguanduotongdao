import logging
from typing import Dict, List, Tuple, Optional
from collections import deque
from datetime import datetime

from app.sensor import SensorData, SensorManager

logger = logging.getLogger(__name__)


class FusionError(Exception):
    """Base exception for fusion-related errors"""
    pass


class DataFusion:
    @staticmethod
    def weighted_average(
        capacitive_value: float,
        ultrasonic_value: float,
        weights: Optional[Dict[str, float]] = None
    ) -> float:
        try:
            if weights is None:
                weights = {"capacitive": 0.6, "ultrasonic": 0.4}
            cap_weight = weights.get("capacitive", 0.6)
            ult_weight = weights.get("ultrasonic", 0.4)
            return capacitive_value * cap_weight + ultrasonic_value * ult_weight
        except Exception as e:
            logger.error(f"加权平均计算失败: {e}")
            raise FusionError(f"加权平均计算失败: {e}") from e

    @staticmethod
    def kalman_filter(
        capacitive_value: float,
        ultrasonic_value: float,
        prev_estimate: float,
        prev_error: float,
        process_noise: float = 0.1,
        measurement_noise: float = 2.0,
        weights: Optional[Dict[str, float]] = None,
    ) -> Tuple[float, float]:
        try:
            fused_raw = DataFusion.weighted_average(capacitive_value, ultrasonic_value, weights)
            prediction = prev_estimate
            prediction_error = prev_error + process_noise
            kalman_gain = prediction_error / (prediction_error + measurement_noise)
            estimate = prediction + kalman_gain * (fused_raw - prediction)
            error = (1 - kalman_gain) * prediction_error
            return estimate, error
        except Exception as e:
            logger.error(f"卡尔曼滤波计算失败: {e}")
            raise FusionError(f"卡尔曼滤波计算失败: {e}") from e

    @staticmethod
    def complementary_filter(
        capacitive_value: float,
        ultrasonic_value: float,
        alpha: float = 0.8,
    ) -> float:
        try:
            return alpha * capacitive_value + (1 - alpha) * ultrasonic_value
        except Exception as e:
            logger.error(f"互补滤波计算失败: {e}")
            raise FusionError(f"互补滤波计算失败: {e}") from e


class ChannelDataBuffer:
    def __init__(self, max_size: int = 100):
        self.buffer = deque(maxlen=max_size)
        self.consecutive_warnings = {
            "high": 0,
            "low": 0,
        }
        self.value_history = deque(maxlen=50)

    def add_data(self, data: SensorData) -> None:
        self.buffer.append(data)
        self.value_history.append((data.timestamp, data.fused_value))

    def get_recent_data(self, count: int = 10) -> List[SensorData]:
        return list(self.buffer)[-count:]

    def get_value_history(self, time_window: int = 5) -> List[Tuple[datetime, float]]:
        if not self.value_history:
            return []
        cutoff_time = datetime.utcnow().timestamp() - time_window
        return [
            (t, v) for t, v in self.value_history
            if t.timestamp() > cutoff_time
        ]

    def increment_consecutive_warning(self, alarm_type: str) -> int:
        if alarm_type in self.consecutive_warnings:
            self.consecutive_warnings[alarm_type] += 1
            return self.consecutive_warnings[alarm_type]
        return 0

    def reset_consecutive_warning(self, alarm_type: str) -> None:
        if alarm_type in self.consecutive_warnings:
            self.consecutive_warnings[alarm_type] = 0

    def reset_all_warnings(self) -> None:
        for key in self.consecutive_warnings:
            self.consecutive_warnings[key] = 0


class FusionManager:
    def __init__(
        self,
        sensor_manager: SensorManager,
        weights: Optional[Dict[str, float]] = None,
        use_kalman: bool = True,
    ):
        self.sensor_manager = sensor_manager
        self.weights = weights or {"capacitive": 0.6, "ultrasonic": 0.4}
        self.use_kalman = use_kalman
        self.buffers: Dict[int, ChannelDataBuffer] = {}
        self._initialize_buffers()

    def _initialize_buffers(self) -> None:
        for channel_id in range(1, self.sensor_manager.num_channels + 1):
            self.buffers[channel_id] = ChannelDataBuffer()

    def process_sensor_data(self, sensor_data: SensorData) -> SensorData:
        try:
            if self.use_kalman:
                prev_estimate, prev_error = self.sensor_manager.get_kalman_state(
                    sensor_data.channel_id
                ) or (50.0, 1.0)
                
                filtered_value, new_error = DataFusion.kalman_filter(
                    sensor_data.capacitive_value,
                    sensor_data.ultrasonic_value,
                    prev_estimate,
                    prev_error,
                    weights=self.weights,
                )
                
                self.sensor_manager.update_kalman_state(
                    sensor_data.channel_id, filtered_value, new_error
                )
                sensor_data.fused_value = round(filtered_value, 3)
            else:
                fused_value = DataFusion.weighted_average(
                    sensor_data.capacitive_value,
                    sensor_data.ultrasonic_value,
                    self.weights,
                )
                sensor_data.fused_value = round(fused_value, 3)

            buffer = self.buffers.get(sensor_data.channel_id)
            if buffer:
                buffer.add_data(sensor_data)

            return sensor_data
        except FusionError as e:
            logger.error(f"数据融合处理失败: {e}")
            raise
        except Exception as e:
            logger.error(f"数据融合发生未知错误: {e}")
            raise FusionError(f"数据融合处理失败: {e}") from e

    def process_batch(self, sensor_data_list: List[SensorData]) -> List[SensorData]:
        fused_data_list = []
        for sensor_data in sensor_data_list:
            try:
                fused_data = self.process_sensor_data(sensor_data)
                fused_data_list.append(fused_data)
            except FusionError as e:
                logger.warning(f"跳过通道 {sensor_data.channel_id} 的数据融合: {e}")
                continue
        return fused_data_list

    def get_buffer(self, channel_id: int) -> Optional[ChannelDataBuffer]:
        return self.buffers.get(channel_id)

    def update_weights(self, capacitive: float, ultrasonic: float) -> None:
        if abs(capacitive + ultrasonic - 1.0) > 0.001:
            raise ValueError("传感器权重之和必须为1.0")
        self.weights = {"capacitive": capacitive, "ultrasonic": ultrasonic}
        logger.info(f"传感器权重已更新: 电容={capacitive}, 超声波={ultrasonic}")

    def get_recent_values(self, channel_id: int, count: int = 10) -> List[float]:
        buffer = self.buffers.get(channel_id)
        if not buffer:
            return []
        recent_data = buffer.get_recent_data(count)
        return [data.fused_value for data in recent_data]
