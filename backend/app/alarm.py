import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import deque
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class AlarmLevel(Enum):
    low = "low"
    medium = "medium"
    high = "high"
    drift = "drift"


class AlarmType(Enum):
    low_threshold = "low_threshold"
    high_threshold = "high_threshold"
    drift = "drift"
    sensor_error = "sensor_error"


class SensorSource(Enum):
    capacitive = "capacitive"
    ultrasonic = "ultrasonic"
    fused = "fused"


@dataclass
class Alarm:
    channel_id: int
    level: AlarmLevel
    alarm_type: AlarmType
    threshold: float
    actual_value: float
    occurred_at: datetime
    description: str
    sensor_source: SensorSource = SensorSource.fused
    resolved: bool = False
    id: Optional[int] = None


class AlarmError(Exception):
    """Base exception for alarm-related errors"""
    pass


class ChannelAlarmConfig:
    def __init__(
        self,
        warning_low: float = 10.0,
        warning_high: float = 90.0,
        drift_threshold: float = 0.5,
        drift_time_window: int = 5,
        enabled_alarms: Optional[List[AlarmType]] = None,
    ):
        self.warning_low = warning_low
        self.warning_high = warning_high
        self.drift_threshold = drift_threshold
        self.drift_time_window = drift_time_window
        self.enabled_alarms = enabled_alarms or [
            AlarmType.low_threshold,
            AlarmType.high_threshold,
            AlarmType.drift,
        ]


class AlarmDetector:
    def __init__(
        self,
        alarm_settings: Optional[Dict] = None,
    ):
        self.alarm_settings = alarm_settings or {
            "consecutive_threshold": 3,
            "drift_detection_window": 5,
            "drift_rate_threshold": 0.1,
        }
        self.channel_configs: Dict[int, ChannelAlarmConfig] = {}
        self.channel_buffers: Dict[int, deque] = {}
        self.drift_history: Dict[int, deque] = {}
        self.active_alarms: Dict[int, List[Alarm]] = {}

    def configure_channel(
        self,
        channel_id: int,
        config: ChannelAlarmConfig,
    ) -> None:
        self.channel_configs[channel_id] = config
        logger.info(f"通道 {channel_id} 报警配置已更新")

    def _get_or_create_buffer(self, channel_id: int) -> deque:
        if channel_id not in self.channel_buffers:
            self.channel_buffers[channel_id] = deque(maxlen=100)
        return self.channel_buffers[channel_id]

    def _get_or_create_drift_history(self, channel_id: int) -> deque:
        if channel_id not in self.drift_history:
            self.drift_history[channel_id] = deque(maxlen=50)
        return self.drift_history[channel_id]

    def _get_or_create_active_alarms(self, channel_id: int) -> List[Alarm]:
        if channel_id not in self.active_alarms:
            self.active_alarms[channel_id] = []
        return self.active_alarms[channel_id]

    def _check_threshold_violation(
        self,
        channel_id: int,
        value: float,
    ) -> Tuple[Optional[AlarmType], float]:
        config = self.channel_configs.get(channel_id)
        if not config:
            return None, 0.0

        if AlarmType.high_threshold in config.enabled_alarms and value > config.warning_high:
            return AlarmType.high_threshold, config.warning_high
        if AlarmType.low_threshold in config.enabled_alarms and value < config.warning_low:
            return AlarmType.low_threshold, config.warning_low
        return None, 0.0

    def _check_drift(
        self,
        channel_id: int,
        current_value: float,
        current_time: datetime,
    ) -> Tuple[bool, float]:
        config = self.channel_configs.get(channel_id)
        if not config or AlarmType.drift not in config.enabled_alarms:
            return False, 0.0

        drift_history = self._get_or_create_drift_history(channel_id)
        drift_history.append((current_time, current_value))

        if len(drift_history) < 2:
            return False, 0.0

        cutoff_time = current_time.timestamp() - config.drift_time_window
        relevant_history = [
            (t, v) for t, v in drift_history
            if t.timestamp() > cutoff_time
        ]

        if len(relevant_history) < 2:
            return False, 0.0

        start_time, start_value = relevant_history[0]
        end_time, end_value = relevant_history[-1]

        time_diff = (end_time - start_time).total_seconds()
        if time_diff < 1:
            return False, 0.0

        value_diff = end_value - start_value
        if abs(value_diff) >= config.drift_threshold:
            return True, value_diff

        return False, 0.0

    def _create_alarm(
        self,
        channel_id: int,
        alarm_type: AlarmType,
        actual_value: float,
        threshold: float,
        occurred_at: datetime,
        sensor_source: SensorSource = SensorSource.fused,
        channel_name: str = "",
        unit: str = "",
    ) -> Alarm:
        if alarm_type == AlarmType.high_threshold:
            level = AlarmLevel.high
            description = (
                f"{channel_name or f'通道{channel_id}'} 液位高于报警上限 {threshold}{unit}, "
                f"当前值: {actual_value}{unit}"
            )
        elif alarm_type == AlarmType.low_threshold:
            level = AlarmLevel.low
            description = (
                f"{channel_name or f'通道{channel_id}'} 液位低于报警下限 {threshold}{unit}, "
                f"当前值: {actual_value}{unit}"
            )
        elif alarm_type == AlarmType.drift:
            level = AlarmLevel.drift
            config = self.channel_configs.get(channel_id)
            drift_threshold = config.drift_threshold if config else 0.5
            description = (
                f"{channel_name or f'通道{channel_id}'} 液位漂移超过阈值 {drift_threshold}{unit}, "
                f"漂移量: {actual_value:.3f}{unit}"
            )
        else:
            level = AlarmLevel.high
            description = f"{channel_name or f'通道{channel_id}'} 未知报警类型"

        alarm = Alarm(
            channel_id=channel_id,
            level=level,
            alarm_type=alarm_type,
            threshold=threshold,
            actual_value=actual_value,
            occurred_at=occurred_at,
            description=description,
            sensor_source=sensor_source,
        )

        active_alarms = self._get_or_create_active_alarms(channel_id)
        active_alarms.append(alarm)
        logger.warning(f"新报警: {description}")
        return alarm

    def process_value(
        self,
        channel_id: int,
        value: float,
        timestamp: datetime,
        sensor_source: SensorSource = SensorSource.fused,
        channel_name: str = "",
        unit: str = "",
    ) -> List[Alarm]:
        alarms: List[Alarm] = []
        consecutive_threshold = self.alarm_settings.get("consecutive_threshold", 3)
        buffer = self._get_or_create_buffer(channel_id)
        buffer.append(value)

        violation_type, threshold = self._check_threshold_violation(channel_id, value)
        if violation_type:
            warning_key = "high" if violation_type == AlarmType.high_threshold else "low"
            consecutive_count = sum(
                1 for v in list(buffer)[-consecutive_threshold:]
                if (warning_key == "high" and v > threshold) or
                   (warning_key == "low" and v < threshold)
            )

            if consecutive_count >= consecutive_threshold:
                alarm = self._create_alarm(
                    channel_id=channel_id,
                    alarm_type=violation_type,
                    actual_value=value,
                    threshold=threshold,
                    occurred_at=timestamp,
                    sensor_source=sensor_source,
                    channel_name=channel_name,
                    unit=unit,
                )
                alarms.append(alarm)

        drift_detected, drift_amount = self._check_drift(channel_id, value, timestamp)
        if drift_detected:
            config = self.channel_configs.get(channel_id)
            drift_threshold = config.drift_threshold if config else 0.5
            alarm = self._create_alarm(
                channel_id=channel_id,
                alarm_type=AlarmType.drift,
                actual_value=drift_amount,
                threshold=drift_threshold,
                occurred_at=timestamp,
                sensor_source=sensor_source,
                channel_name=channel_name,
                unit=unit,
            )
            alarms.append(alarm)

        return alarms

    def resolve_alarm(self, channel_id: int, alarm_index: int) -> bool:
        active_alarms = self._get_or_create_active_alarms(channel_id)
        if 0 <= alarm_index < len(active_alarms):
            active_alarms[alarm_index].resolved = True
            logger.info(f"通道 {channel_id} 报警已解除: {active_alarms[alarm_index].description}")
            return True
        return False

    def get_active_alarms(self, channel_id: Optional[int] = None) -> List[Alarm]:
        if channel_id is not None:
            return [a for a in self._get_or_create_active_alarms(channel_id) if not a.resolved]
        all_alarms = []
        for alarms in self.active_alarms.values():
            all_alarms.extend([a for a in alarms if not a.resolved])
        return all_alarms

    def get_channel_status(self, channel_id: int) -> Dict:
        buffer = self._get_or_create_buffer(channel_id)
        drift_history = list(self._get_or_create_drift_history(channel_id))
        active_alarms = self.get_active_alarms(channel_id)

        return {
            "channel_id": channel_id,
            "active_alarm_count": len(active_alarms),
            "recent_values": list(buffer)[-10:],
            "drift_history_count": len(drift_history),
            "latest_value": buffer[-1] if buffer else None,
        }

    def reset_channel(self, channel_id: int) -> None:
        if channel_id in self.channel_buffers:
            self.channel_buffers[channel_id].clear()
        if channel_id in self.drift_history:
            self.drift_history[channel_id].clear()
        if channel_id in self.active_alarms:
            del self.active_alarms[channel_id]
        logger.info(f"通道 {channel_id} 报警状态已重置")
