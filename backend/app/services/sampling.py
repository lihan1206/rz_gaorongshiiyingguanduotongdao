from datetime import datetime

from sqlalchemy.orm import Session

from app.models.alarm import Alarm, AlarmLevel
from app.models.channel import Channel
from app.models.liquid_level_data import DataStatus, LiquidLevelData
from app.schemas.sample import SyncSampleRequest


def classify_status(channel: Channel, value: float) -> DataStatus:
    if value < channel.range_min or value > channel.range_max:
        return DataStatus.error
    if value < channel.warning_low or value > channel.warning_high:
        return DataStatus.warning
    return DataStatus.normal


def create_alarm_if_needed(db: Session, channel: Channel, value: float, sample_time: datetime) -> None:
    if not channel.alarm_enabled:
        return

    if value < channel.warning_low:
        alarm = Alarm(
            channel_id=channel.id,
            level=AlarmLevel.low,
            threshold=channel.warning_low,
            actual_value=value,
            occurred_at=sample_time,
            description=f"{channel.name} 液位低于报警下限 {channel.warning_low}{channel.unit}",
        )
        db.add(alarm)
        return

    if value > channel.warning_high:
        alarm = Alarm(
            channel_id=channel.id,
            level=AlarmLevel.high,
            threshold=channel.warning_high,
            actual_value=value,
            occurred_at=sample_time,
            description=f"{channel.name} 液位高于报警上限 {channel.warning_high}{channel.unit}",
        )
        db.add(alarm)


def ingest_sync_samples(db: Session, payload: SyncSampleRequest) -> list[LiquidLevelData]:
    sample_time = payload.sample_time or datetime.utcnow()
    point_map = {point.channel_id: point.value for point in payload.values}
    channels = db.query(Channel).filter(Channel.id.in_(point_map.keys())).all()

    if len(channels) != len(point_map):
        missing_ids = sorted(set(point_map.keys()) - {channel.id for channel in channels})
        raise ValueError(f"通道不存在: {missing_ids}")

    records: list[LiquidLevelData] = []
    for channel in channels:
        actual_value = point_map[channel.id] + channel.calibration_offset
        status = classify_status(channel, actual_value)
        data = LiquidLevelData(
            channel_id=channel.id,
            value=actual_value,
            sample_time=sample_time,
            temperature=payload.temperature,
            status=status,
        )
        db.add(data)
        create_alarm_if_needed(db, channel, actual_value, sample_time)
        records.append(data)

    db.commit()
    for record in records:
        db.refresh(record)
    return records
