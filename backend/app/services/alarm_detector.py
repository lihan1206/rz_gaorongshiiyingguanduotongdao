from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import deque
import logging

from sqlalchemy.orm import Session

from app.core.config import AppConfig
from app.models.alarm import Alarm, AlarmLevel, AlarmType, SensorSource
from app.models.channel import Channel, AlarmType as ChannelAlarmType
from app.services.sensor_fusion import SensorData, ChannelDataBuffer

logger = logging.getLogger(__name__)


class AlarmDetector:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.alarm_settings = AppConfig.get_alarm_settings()
        self.channel_buffers: Dict[int, ChannelDataBuffer] = {}
        self.drift_history: Dict[int, deque] = {}

    def _get_or_create_buffer(self, channel_id: int) -> ChannelDataBuffer:
        if channel_id not in self.channel_buffers:
            self.channel_buffers[channel_id] = ChannelDataBuffer()
        return self.channel_buffers[channel_id]

    def _get_or_create_drift_history(self, channel_id: int) -> deque:
        if channel_id not in self.drift_history:
            self.drift_history[channel_id] = deque(maxlen=50)
        return self.drift_history[channel_id]

    def _check_threshold_violation(
        self,
        channel: Channel,
        value: float,
    ) -> Tuple[Optional[AlarmType], float]:
        enabled_types = channel.get_enabled_alarm_types()

        if ChannelAlarmType.high in enabled_types and value > channel.warning_high:
            return AlarmType.high_threshold, channel.warning_high
        if ChannelAlarmType.low in enabled_types and value < channel.warning_low:
            return AlarmType.low_threshold, channel.warning_low
        return None, 0.0

    def _check_drift(
        self,
        channel: Channel,
        current_value: float,
        current_time: datetime,
    ) -> Tuple[bool, float]:
        if ChannelAlarmType.drift not in channel.get_enabled_alarm_types():
            return False, 0.0

        drift_history = self._get_or_create_drift_history(channel.id)
        drift_history.append((current_time, current_value))

        if len(drift_history) < 2:
            return False, 0.0

        drift_threshold = channel.drift_threshold
        time_window = channel.drift_time_window

        cutoff_time = current_time.timestamp() - time_window
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
        drift_rate = value_diff / time_diff

        if abs(value_diff) >= drift_threshold:
            return True, value_diff

        return False, 0.0

    def _create_alarm(
        self,
        channel: Channel,
        alarm_type: AlarmType,
        actual_value: float,
        threshold: float,
        occurred_at: datetime,
        sensor_source: SensorSource = SensorSource.fused,
    ) -> Alarm:
        if alarm_type == AlarmType.high_threshold:
            level = AlarmLevel.high
            description = (
                f"{channel.name} 液位高于报警上限 {threshold}{channel.unit}, "
                f"当前值: {actual_value}{channel.unit}"
            )
        elif alarm_type == AlarmType.low_threshold:
            level = AlarmLevel.low
            description = (
                f"{channel.name} 液位低于报警下限 {threshold}{channel.unit}, "
                f"当前值: {actual_value}{channel.unit}"
            )
        elif alarm_type == AlarmType.drift:
            level = AlarmLevel.drift
            description = (
                f"{channel.name} 液位漂移超过阈值 {channel.drift_threshold}{channel.unit}, "
                f"漂移量: {actual_value:.3f}{channel.unit}"
            )
        else:
            level = AlarmLevel.high
            description = f"{channel.name} 未知报警类型"

        alarm = Alarm(
            channel_id=channel.id,
            level=level,
            alarm_type=alarm_type,
            threshold=threshold,
            actual_value=actual_value,
            occurred_at=occurred_at,
            description=description,
            sensor_source=sensor_source,
            resolved=False,
        )
        self.db.add(alarm)
        return alarm

    def process_sensor_data(
        self,
        channel: Channel,
        sensor_data: SensorData,
    ) -> List[Alarm]:
        if not channel.alarm_enabled:
            return []

        buffer = self._get_or_create_buffer(channel.id)
        buffer.add_data(sensor_data)

        alarms: List[Alarm] = []
        consecutive_threshold = self.alarm_settings.get("consecutive_threshold", 3)

        violation_type, threshold = self._check_threshold_violation(
            channel, sensor_data.fused_value
        )

        if violation_type:
            warning_key = "high" if violation_type == AlarmType.high_threshold else "low"
            consecutive_count = buffer.increment_consecutive_warning(warning_key)

            if consecutive_count >= consecutive_threshold:
                alarm = self._create_alarm(
                    channel=channel,
                    alarm_type=violation_type,
                    actual_value=sensor_data.fused_value,
                    threshold=threshold,
                    occurred_at=sensor_data.timestamp,
                )
                alarms.append(alarm)
                buffer.reset_consecutive_warning(warning_key)
        else:
            buffer.reset_all_warnings()

        drift_detected, drift_amount = self._check_drift(
            channel, sensor_data.fused_value, sensor_data.timestamp
        )

        if drift_detected:
            alarm = self._create_alarm(
                channel=channel,
                alarm_type=AlarmType.drift,
                actual_value=drift_amount,
                threshold=channel.drift_threshold,
                occurred_at=sensor_data.timestamp,
            )
            alarms.append(alarm)

        if alarms:
            self.db.commit()
            for alarm in alarms:
                self.db.refresh(alarm)

        return alarms

    def process_multi_channel_data(
        self,
        channels: List[Channel],
        sensor_data_list: List[SensorData],
    ) -> List[Alarm]:
        channel_map = {c.id: c for c in channels}
        all_alarms: List[Alarm] = []

        for data in sensor_data_list:
            if data.channel_id in channel_map:
                alarms = self.process_sensor_data(
                    channel_map[data.channel_id],
                    data,
                )
                all_alarms.extend(alarms)

        return all_alarms

    def get_channel_status(self, channel_id: int) -> Dict:
        buffer = self._get_or_create_buffer(channel_id)
        recent_data = buffer.get_recent_data(10)
        drift_history = list(self._get_or_create_drift_history(channel_id))

        return {
            "channel_id": channel_id,
            "consecutive_warnings": dict(buffer.consecutive_warnings),
            "recent_data_count": len(recent_data),
            "drift_history_count": len(drift_history),
            "latest_value": recent_data[-1].fused_value if recent_data else None,
        }

    def reset_channel(self, channel_id: int) -> None:
        if channel_id in self.channel_buffers:
            self.channel_buffers[channel_id].reset_all_warnings()
        if channel_id in self.drift_history:
            self.drift_history[channel_id].clear()
