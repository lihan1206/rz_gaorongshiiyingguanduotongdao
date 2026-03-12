import logging
from datetime import datetime, timedelta
from math import sin

from sqlalchemy.orm import Session

from app.models.channel import Channel, ChannelStatus, SensorType
from app.models.liquid_level_data import LiquidLevelData
from app.models.user import User, UserRole
from app.services.sampling import classify_status

logger = logging.getLogger(__name__)


def seed_users(db: Session) -> None:
    if db.query(User).count() > 0:
        return

    users = [
        User(username="admin", password="123456", role=UserRole.admin),
        User(username="operator", password="123456", role=UserRole.operator),
        User(username="viewer", password="123456", role=UserRole.viewer),
    ]
    db.add_all(users)
    db.commit()


def seed_channels(db: Session) -> list[Channel]:
    existing = db.query(Channel).count()
    if existing > 0:
        return db.query(Channel).order_by(Channel.id.asc()).all()

    channels = []
    for idx in range(1, 9):
        channel = Channel(
            name=f"石英管-{idx:02d}",
            sensor_type=SensorType.capacitive if idx % 2 == 0 else SensorType.laser,
            range_min=0,
            range_max=200,
            unit="mm",
            calibration_offset=0,
            warning_low=25,
            warning_high=175,
            alarm_enabled=True,
            status=ChannelStatus.active,
        )
        channels.append(channel)

    db.add_all(channels)
    db.commit()
    for channel in channels:
        db.refresh(channel)
    return channels


def seed_history_data(db: Session, channels: list[Channel]) -> None:
    if db.query(LiquidLevelData).count() > 0:
        return

    now = datetime.utcnow().replace(second=0, microsecond=0)
    records: list[LiquidLevelData] = []

    for step in range(120):
        sample_time = now - timedelta(minutes=120 - step)
        for channel in channels:
            baseline = 95 + channel.id * 6
            wave = sin((step + channel.id) / 5) * 28
            drift = (channel.id % 3 - 1) * 3
            value = round(baseline + wave + drift + channel.calibration_offset, 2)
            status = classify_status(channel, value)
            records.append(
                LiquidLevelData(
                    channel_id=channel.id,
                    value=value,
                    sample_time=sample_time,
                    temperature=950 + channel.id,
                    status=status,
                )
            )

    db.add_all(records)
    db.commit()


def run_seed(db: Session) -> None:
    seed_users(db)
    channels = seed_channels(db)
    seed_history_data(db, channels)
    logger.info("数据库初始化完成，已写入用户、通道及历史采样数据")
