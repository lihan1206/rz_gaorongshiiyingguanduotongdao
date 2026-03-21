import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.alarm import Alarm, AlarmLevel
from app.models.channel import AlarmType, Channel
from app.models.liquid_level_data import DataStatus, LiquidLevelData
from app.schemas.sample import SyncSampleRequest

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "core" / "config.json"


def load_config() -> Dict[str, Any]:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"加载配置文件失败: {e}, 使用默认配置")
        return {
            "alarm_consecutive_count": 3,
            "drift_detection": {
                "enabled": True,
                "window_seconds": 5,
                "threshold_mm": 0.5,
            },
        }


_exceed_count: Dict[int, int] = defaultdict(int)
_value_history: Dict[int, List[tuple]] = defaultdict(list)


def reset_alarm_state(channel_id: int) -> None:
    _exceed_count[channel_id] = 0


def classify_status(channel: Channel, value: float) -> DataStatus:
    if value < channel.range_min or value > channel.range_max:
        return DataStatus.error
    if value < channel.warning_low or value > channel.warning_high:
        return DataStatus.warning
    return DataStatus.normal


def fuse_sensor_values(
    value_a: Optional[float],
    value_b: Optional[float],
    weight_a: float,
    weight_b: float,
) -> float:
    if value_a is not None and value_b is not None:
        return value_a * weight_a + value_b * weight_b
    elif value_a is not None:
        return value_a
    elif value_b is not None:
        return value_b
    else:
        raise ValueError("至少需要一个传感器的值")


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

    history = _value_history[channel_id]
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


def create_alarm_if_needed(
    db: Session,
    channel: Channel,
    fused_value: float,
    value_a: Optional[float],
    value_b: Optional[float],
    sample_time: datetime,
    config: Dict[str, Any],
) -> Optional[Alarm]:
    if not channel.alarm_enabled:
        return None

    consecutive_count = config.get("alarm_consecutive_count", 3)
    sensor_source = "fusion"
    if value_a is not None and value_b is None:
        sensor_source = f"sensor_a:{channel.sensor_type_a.value}"
    elif value_b is not None and value_a is None:
        sensor_source = f"sensor_b:{channel.sensor_type_b.value if channel.sensor_type_b else 'unknown'}"
    elif value_a is not None and value_b is not None:
        sensor_source = f"fusion:{channel.sensor_type_a.value}+{channel.sensor_type_b.value if channel.sensor_type_b else 'unknown'}"

    if channel.alarm_type == AlarmType.high:
        if fused_value > channel.warning_high:
            _exceed_count[channel.id] += 1
            if _exceed_count[channel.id] >= consecutive_count:
                _exceed_count[channel.id] = 0
                alarm = Alarm(
                    channel_id=channel.id,
                    level=AlarmLevel.high,
                    threshold=channel.warning_high,
                    actual_value=fused_value,
                    value_a=value_a,
                    value_b=value_b,
                    sensor_source=sensor_source,
                    occurred_at=sample_time,
                    description=f"{channel.name} 液位高于报警上限 {channel.warning_high}{channel.unit}",
                )
                db.add(alarm)
                return alarm
        else:
            _exceed_count[channel.id] = 0

    elif channel.alarm_type == AlarmType.low:
        if fused_value < channel.warning_low:
            _exceed_count[channel.id] += 1
            if _exceed_count[channel.id] >= consecutive_count:
                _exceed_count[channel.id] = 0
                alarm = Alarm(
                    channel_id=channel.id,
                    level=AlarmLevel.low,
                    threshold=channel.warning_low,
                    actual_value=fused_value,
                    value_a=value_a,
                    value_b=value_b,
                    sensor_source=sensor_source,
                    occurred_at=sample_time,
                    description=f"{channel.name} 液位低于报警下限 {channel.warning_low}{channel.unit}",
                )
                db.add(alarm)
                return alarm
        else:
            _exceed_count[channel.id] = 0

    elif channel.alarm_type == AlarmType.drift:
        if check_drift_alarm(channel.id, fused_value, sample_time, config):
            alarm = Alarm(
                channel_id=channel.id,
                level=AlarmLevel.drift,
                threshold=config.get("drift_detection", {}).get("threshold_mm", 0.5),
                actual_value=fused_value,
                value_a=value_a,
                value_b=value_b,
                sensor_source=sensor_source,
                occurred_at=sample_time,
                description=f"{channel.name} 液位漂移报警，检测到液位连续下降",
            )
            db.add(alarm)
            return alarm

    return None


def ingest_sync_samples(db: Session, payload: SyncSampleRequest) -> List[LiquidLevelData]:
    config = load_config()
    sample_time = payload.sample_time or datetime.utcnow()
    point_map = {point.channel_id: point for point in payload.values}
    channels = db.query(Channel).filter(Channel.id.in_(point_map.keys())).all()

    if len(channels) != len(point_map):
        missing_ids = sorted(set(point_map.keys()) - {channel.id for channel in channels})
        raise ValueError(f"通道不存在: {missing_ids}")

    records: List[LiquidLevelData] = []
    for channel in channels:
        point = point_map[channel.id]
        value_a = point.value_a
        value_b = point.value_b

        if value_a is not None:
            value_a = value_a + channel.calibration_offset_a
        if value_b is not None:
            value_b = value_b + channel.calibration_offset_b

        fused_value = fuse_sensor_values(
            value_a,
            value_b,
            channel.fusion_weight_a,
            channel.fusion_weight_b,
        )

        status = classify_status(channel, fused_value)

        data = LiquidLevelData(
            channel_id=channel.id,
            value_a=value_a,
            value_b=value_b,
            fused_value=fused_value,
            sample_time=sample_time,
            temperature=payload.temperature,
            status=status,
        )
        db.add(data)

        create_alarm_if_needed(
            db,
            channel,
            fused_value,
            value_a,
            value_b,
            sample_time,
            config,
        )

        records.append(data)

    db.commit()
    for record in records:
        db.refresh(record)
    return records
