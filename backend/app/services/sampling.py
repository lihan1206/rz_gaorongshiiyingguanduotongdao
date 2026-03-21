from datetime import datetime
from typing import List, Dict, Any

from sqlalchemy.orm import Session

from app.models.alarm import Alarm, AlarmLevel, AlarmType, SensorSource
from app.models.channel import Channel
from app.models.liquid_level_data import DataStatus, LiquidLevelData
from app.schemas.sample import SyncSampleRequest, MultiSensorSampleRequest
from app.services.sensor_fusion import DataFusion, SensorData


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
            alarm_type=AlarmType.low_threshold,
            threshold=channel.warning_low,
            actual_value=value,
            occurred_at=sample_time,
            description=f"{channel.name} 液位低于报警下限 {channel.warning_low}{channel.unit}",
            sensor_source=SensorSource.fused,
        )
        db.add(alarm)
        return

    if value > channel.warning_high:
        alarm = Alarm(
            channel_id=channel.id,
            level=AlarmLevel.high,
            alarm_type=AlarmType.high_threshold,
            threshold=channel.warning_high,
            actual_value=value,
            occurred_at=sample_time,
            description=f"{channel.name} 液位高于报警上限 {channel.warning_high}{channel.unit}",
            sensor_source=SensorSource.fused,
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
            capacitive_value=actual_value,
            ultrasonic_value=actual_value,
            fused_value=actual_value,
            sample_time=sample_time,
            temperature=payload.temperature,
            status=status,
            sensor_source=SensorSource.fused,
        )
        db.add(data)
        create_alarm_if_needed(db, channel, actual_value, sample_time)
        records.append(data)

    db.commit()
    for record in records:
        db.refresh(record)
    return records


def ingest_multi_sensor_samples(
    db: Session,
    payload: MultiSensorSampleRequest,
) -> List[LiquidLevelData]:
    sample_time = payload.sample_time or datetime.utcnow()
    channel_data: Dict[int, Dict[str, Any]] = {}

    for point in payload.values:
        if point.channel_id not in channel_data:
            channel_data[point.channel_id] = {
                "capacitive": None,
                "ultrasonic": None,
            }
        channel_data[point.channel_id][point.sensor_type] = point.value

    channel_ids = list(channel_data.keys())
    channels = db.query(Channel).filter(Channel.id.in_(channel_ids)).all()

    if len(channels) != len(channel_data):
        missing_ids = sorted(set(channel_data.keys()) - {channel.id for channel in channels})
        raise ValueError(f"通道不存在: {missing_ids}")

    records: List[LiquidLevelData] = []
    sensor_data_list: List[SensorData] = []

    for channel in channels:
        data = channel_data[channel.id]
        cap_value = data.get("capacitive") or data.get("ultrasonic") or 0.0
        ult_value = data.get("ultrasonic") or data.get("capacitive") or 0.0

        fused_value = DataFusion.weighted_average(cap_value, ult_value)
        actual_value = fused_value + channel.calibration_offset
        status = classify_status(channel, actual_value)

        sensor_data = SensorData(
            channel_id=channel.id,
            capacitive_value=cap_value,
            ultrasonic_value=ult_value,
            fused_value=actual_value,
            temperature=payload.temperature,
            timestamp=sample_time,
        )
        sensor_data_list.append(sensor_data)

        db_data = LiquidLevelData(
            channel_id=channel.id,
            value=actual_value,
            capacitive_value=cap_value,
            ultrasonic_value=ult_value,
            fused_value=actual_value,
            sample_time=sample_time,
            temperature=payload.temperature,
            status=status,
            sensor_source=SensorSource.fused,
        )
        db.add(db_data)
        records.append(db_data)

    from app.services.alarm_detector import AlarmDetector
    alarm_detector = AlarmDetector(db)
    alarm_detector.process_multi_channel_data(channels, sensor_data_list)

    db.commit()
    for record in records:
        db.refresh(record)
    return records


def ingest_fused_sensor_data(
    db: Session,
    sensor_data_list: List[SensorData],
) -> List[LiquidLevelData]:
    channel_ids = [data.channel_id for data in sensor_data_list]
    channels = db.query(Channel).filter(Channel.id.in_(channel_ids)).all()
    channel_map = {c.id: c for c in channels}

    records: List[LiquidLevelData] = []
    for sensor_data in sensor_data_list:
        channel = channel_map.get(sensor_data.channel_id)
        if not channel:
            continue

        status = classify_status(channel, sensor_data.fused_value)
        db_data = LiquidLevelData(
            channel_id=sensor_data.channel_id,
            value=sensor_data.fused_value,
            capacitive_value=sensor_data.capacitive_value,
            ultrasonic_value=sensor_data.ultrasonic_value,
            fused_value=sensor_data.fused_value,
            sample_time=sensor_data.timestamp,
            temperature=sensor_data.temperature,
            status=status,
            sensor_source=SensorSource.fused,
        )
        db.add(db_data)
        records.append(db_data)

    from app.services.alarm_detector import AlarmDetector
    alarm_detector = AlarmDetector(db)
    alarm_detector.process_multi_channel_data(channels, sensor_data_list)

    db.commit()
    for record in records:
        db.refresh(record)
    return records
