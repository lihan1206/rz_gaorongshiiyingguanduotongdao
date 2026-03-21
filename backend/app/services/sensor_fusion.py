import random
import time
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from collections import deque
from dataclasses import dataclass

from app.core.config import AppConfig


@dataclass
class SensorData:
    channel_id: int
    capacitive_value: float
    ultrasonic_value: float
    fused_value: float
    temperature: Optional[float] = None
    timestamp: datetime = None


class SensorSimulator:
    def __init__(self, base_value: float = 50.0, noise_level: float = 2.0):
        self.base_value = base_value
        self.noise_level = noise_level
        self.current_value = base_value
        self._drift_start = None
        self._drift_rate = 0.0

    def start_drift(self, rate: float = -0.1):
        self._drift_start = time.time()
        self._drift_rate = rate

    def stop_drift(self):
        self._drift_start = None

    def read_capacitive(self) -> float:
        noise = random.uniform(-self.noise_level, self.noise_level)
        drift = 0.0
        if self._drift_start:
            drift = self._drift_rate * (time.time() - self._drift_start)
        return max(0.0, min(100.0, self.current_value + noise + drift))

    def read_ultrasonic(self) -> float:
        noise = random.uniform(-self.noise_level * 1.5, self.noise_level * 1.5)
        drift = 0.0
        if self._drift_start:
            drift = self._drift_rate * (time.time() - self._drift_start)
        return max(0.0, min(100.0, self.current_value + noise + drift))


class DataFusion:
    @staticmethod
    def weighted_average(capacitive_value: float, ultrasonic_value: float) -> float:
        weights = AppConfig.get_sensor_weights()
        cap_weight = weights.get("capacitive", 0.6)
        ult_weight = weights.get("ultrasonic", 0.4)
        return capacitive_value * cap_weight + ultrasonic_value * ult_weight

    @staticmethod
    def kalman_filter(
        capacitive_value: float,
        ultrasonic_value: float,
        prev_estimate: float,
        prev_error: float,
        process_noise: float = 0.1,
        measurement_noise: float = 2.0,
    ) -> Tuple[float, float]:
        fused_raw = DataFusion.weighted_average(capacitive_value, ultrasonic_value)
        prediction = prev_estimate
        prediction_error = prev_error + process_noise
        kalman_gain = prediction_error / (prediction_error + measurement_noise)
        estimate = prediction + kalman_gain * (fused_raw - prediction)
        error = (1 - kalman_gain) * prediction_error
        return estimate, error


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


class SensorManager:
    def __init__(self, num_channels: int = 8):
        self.num_channels = num_channels
        self.simulators: Dict[int, SensorSimulator] = {}
        self.buffers: Dict[int, ChannelDataBuffer] = {}
        self.kalman_state: Dict[int, Tuple[float, float]] = {}

        for channel_id in range(1, num_channels + 1):
            self.simulators[channel_id] = SensorSimulator(
                base_value=50.0 + random.uniform(-10, 10)
            )
            self.buffers[channel_id] = ChannelDataBuffer()
            self.kalman_state[channel_id] = (50.0, 1.0)

    def read_channel(self, channel_id: int, temperature: Optional[float] = None) -> SensorData:
        if channel_id not in self.simulators:
            raise ValueError(f"Channel {channel_id} not found")

        simulator = self.simulators[channel_id]
        cap_value = simulator.read_capacitive()
        ult_value = simulator.read_ultrasonic()
        fused_value = DataFusion.weighted_average(cap_value, ult_value)

        prev_estimate, prev_error = self.kalman_state[channel_id]
        filtered_value, new_error = DataFusion.kalman_filter(
            cap_value, ult_value, prev_estimate, prev_error
        )
        self.kalman_state[channel_id] = (filtered_value, new_error)

        sensor_data = SensorData(
            channel_id=channel_id,
            capacitive_value=round(cap_value, 3),
            ultrasonic_value=round(ult_value, 3),
            fused_value=round(filtered_value, 3),
            temperature=temperature,
            timestamp=datetime.utcnow(),
        )

        self.buffers[channel_id].add_data(sensor_data)
        return sensor_data

    def read_all_channels(self, temperature: Optional[float] = None) -> List[SensorData]:
        return [
            self.read_channel(channel_id, temperature)
            for channel_id in self.simulators.keys()
        ]

    def get_buffer(self, channel_id: int) -> Optional[ChannelDataBuffer]:
        return self.buffers.get(channel_id)

    def start_drift(self, channel_id: int, rate: float = -0.1) -> None:
        if channel_id in self.simulators:
            self.simulators[channel_id].start_drift(rate)

    def stop_drift(self, channel_id: int) -> None:
        if channel_id in self.simulators:
            self.simulators[channel_id].stop_drift()
