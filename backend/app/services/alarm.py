import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class AlarmType(str, Enum):
    high = "high"
    low = "low"
    drift = "drift"


class AlarmLevel(str, Enum):
    low = "low"
    high = "high"
    drift = "drift"


class AlarmPriority(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


@dataclass
class AlarmCondition:
    alarm_type: AlarmType
    threshold: float
    consecutive_count: int = 3
    enabled: bool = True


@dataclass
class DriftConfig:
    enabled: bool = True
    window_seconds: int = 5
    threshold_mm: float = 0.5


@dataclass
class AlarmEvent:
    channel_id: int
    level: AlarmLevel
    threshold: float
    actual_value: float
    value_a: Optional[float]
    value_b: Optional[float]
    sensor_source: str
    occurred_at: datetime
    description: str
    priority: AlarmPriority = AlarmPriority.medium


class AlarmError(Exception):
    pass


class AlarmManager:
    def __init__(self):
        self._exceed_count: Dict[int, int] = defaultdict(int)
        self._value_history: Dict[int, List[tuple]] = defaultdict(list)
        self._alarm_callbacks: List[Callable[[AlarmEvent], None]] = []
        self._drift_config = DriftConfig()

    def set_drift_config(self, config: Dict[str, Any]) -> None:
        self._drift_config = DriftConfig(
            enabled=config.get("enabled", True),
            window_seconds=config.get("window_seconds", 5),
            threshold_mm=config.get("threshold_mm", 0.5),
        )

    def reset_channel_state(self, channel_id: int) -> None:
        self._exceed_count[channel_id] = 0
        self._value_history[channel_id] = []
        logger.debug(f"通道 {channel_id} 报警状态已重置")

    def register_callback(self, callback: Callable[[AlarmEvent], None]) -> None:
        self._alarm_callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[AlarmEvent], None]) -> None:
        if callback in self._alarm_callbacks:
            self._alarm_callbacks.remove(callback)

    def _notify_callbacks(self, event: AlarmEvent) -> None:
        for callback in self._alarm_callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"报警回调执行失败: {e}")

    def check_high_alarm(
        self,
        channel_id: int,
        channel_name: str,
        value: float,
        threshold: float,
        consecutive_count: int,
        value_a: Optional[float],
        value_b: Optional[float],
        sensor_source: str,
        sample_time: datetime,
        unit: str = "mm",
    ) -> Optional[AlarmEvent]:
        if value > threshold:
            self._exceed_count[channel_id] += 1
            logger.debug(
                f"通道 {channel_id} 高液位超限计数: {self._exceed_count[channel_id]}/{consecutive_count}"
            )

            if self._exceed_count[channel_id] >= consecutive_count:
                self._exceed_count[channel_id] = 0
                event = AlarmEvent(
                    channel_id=channel_id,
                    level=AlarmLevel.high,
                    threshold=threshold,
                    actual_value=value,
                    value_a=value_a,
                    value_b=value_b,
                    sensor_source=sensor_source,
                    occurred_at=sample_time,
                    description=f"{channel_name} 液位高于报警上限 {threshold}{unit}",
                    priority=AlarmPriority.high,
                )
                self._notify_callbacks(event)
                return event
        else:
            self._exceed_count[channel_id] = 0

        return None

    def check_low_alarm(
        self,
        channel_id: int,
        channel_name: str,
        value: float,
        threshold: float,
        consecutive_count: int,
        value_a: Optional[float],
        value_b: Optional[float],
        sensor_source: str,
        sample_time: datetime,
        unit: str = "mm",
    ) -> Optional[AlarmEvent]:
        if value < threshold:
            self._exceed_count[channel_id] += 1
            logger.debug(
                f"通道 {channel_id} 低液位超限计数: {self._exceed_count[channel_id]}/{consecutive_count}"
            )

            if self._exceed_count[channel_id] >= consecutive_count:
                self._exceed_count[channel_id] = 0
                event = AlarmEvent(
                    channel_id=channel_id,
                    level=AlarmLevel.low,
                    threshold=threshold,
                    actual_value=value,
                    value_a=value_a,
                    value_b=value_b,
                    sensor_source=sensor_source,
                    occurred_at=sample_time,
                    description=f"{channel_name} 液位低于报警下限 {threshold}{unit}",
                    priority=AlarmPriority.high,
                )
                self._notify_callbacks(event)
                return event
        else:
            self._exceed_count[channel_id] = 0

        return None

    def check_drift_alarm(
        self,
        channel_id: int,
        channel_name: str,
        value: float,
        sample_time: datetime,
        value_a: Optional[float],
        value_b: Optional[float],
        sensor_source: str,
    ) -> Optional[AlarmEvent]:
        if not self._drift_config.enabled:
            return None

        window_seconds = self._drift_config.window_seconds
        threshold_mm = self._drift_config.threshold_mm

        history = self._value_history[channel_id]
        cutoff_time = sample_time - timedelta(seconds=window_seconds)
        history[:] = [(t, v) for t, v in history if t >= cutoff_time]

        history.append((sample_time, value))

        if len(history) >= 2:
            oldest_time, oldest_value = history[0]
            time_diff = (sample_time - oldest_time).total_seconds()

            if time_diff >= window_seconds:
                value_diff = oldest_value - value
                if value_diff >= threshold_mm:
                    event = AlarmEvent(
                        channel_id=channel_id,
                        level=AlarmLevel.drift,
                        threshold=threshold_mm,
                        actual_value=value,
                        value_a=value_a,
                        value_b=value_b,
                        sensor_source=sensor_source,
                        occurred_at=sample_time,
                        description=f"{channel_name} 液位漂移报警，检测到液位连续下降 {value_diff:.2f}mm",
                        priority=AlarmPriority.medium,
                    )
                    self._notify_callbacks(event)
                    return event

        return None

    def check_alarm(
        self,
        channel_id: int,
        channel_name: str,
        value: float,
        alarm_type: AlarmType,
        warning_low: float,
        warning_high: float,
        consecutive_count: int,
        value_a: Optional[float],
        value_b: Optional[float],
        sensor_source: str,
        sample_time: datetime,
        unit: str = "mm",
        alarm_enabled: bool = True,
    ) -> Optional[AlarmEvent]:
        if not alarm_enabled:
            return None

        if alarm_type == AlarmType.high:
            return self.check_high_alarm(
                channel_id,
                channel_name,
                value,
                warning_high,
                consecutive_count,
                value_a,
                value_b,
                sensor_source,
                sample_time,
                unit,
            )
        elif alarm_type == AlarmType.low:
            return self.check_low_alarm(
                channel_id,
                channel_name,
                value,
                warning_low,
                consecutive_count,
                value_a,
                value_b,
                sensor_source,
                sample_time,
                unit,
            )
        elif alarm_type == AlarmType.drift:
            return self.check_drift_alarm(
                channel_id,
                channel_name,
                value,
                sample_time,
                value_a,
                value_b,
                sensor_source,
            )

        return None

    def get_channel_state(self, channel_id: int) -> Dict[str, Any]:
        return {
            "exceed_count": self._exceed_count[channel_id],
            "history_length": len(self._value_history[channel_id]),
        }


alarm_manager = AlarmManager()


def get_alarm_manager() -> AlarmManager:
    return alarm_manager


def check_drift_alarm(
    channel_id: int,
    current_value: float,
    current_time: datetime,
    config: Dict[str, Any],
) -> bool:
    drift_config = config.get("drift_detection", {})
    if not drift_config.get("enabled", True):
        return False

    window_seconds = drift_config.get("window_seconds", 5)
    threshold_mm = drift_config.get("threshold_mm", 0.5)

    history = alarm_manager._value_history[channel_id]
    cutoff_time = current_time - timedelta(seconds=window_seconds)
    history[:] = [(t, v) for t, v in history if t >= cutoff_time]

    history.append((current_time, current_value))

    if len(history) >= 2:
        oldest_time, oldest_value = history[0]
        time_diff = (current_time - oldest_time).total_seconds()

        if time_diff >= window_seconds:
            value_diff = oldest_value - current_value
            if value_diff >= threshold_mm:
                return True

    return False


def reset_alarm_state(channel_id: int) -> None:
    alarm_manager.reset_channel_state(channel_id)
