from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SensorType(str, Enum):
    capacitive = "capacitive"
    ultrasonic = "ultrasonic"
    laser = "laser"


class AlarmType(str, Enum):
    high = "high"
    low = "low"
    drift = "drift"


class ChannelStatus(str, Enum):
    active = "active"
    inactive = "inactive"


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    sensor_type_a: Mapped[SensorType] = mapped_column(SQLEnum(SensorType), nullable=False, default=SensorType.capacitive)
    sensor_type_b: Mapped[Optional[SensorType]] = mapped_column(SQLEnum(SensorType), nullable=True, default=SensorType.ultrasonic)
    range_min: Mapped[float] = mapped_column(Float, nullable=False)
    range_max: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(10), default="mm")
    calibration_offset_a: Mapped[float] = mapped_column(Float, default=0.0)
    calibration_offset_b: Mapped[float] = mapped_column(Float, default=0.0)
    fusion_weight_a: Mapped[float] = mapped_column(Float, default=0.5)
    fusion_weight_b: Mapped[float] = mapped_column(Float, default=0.5)
    warning_low: Mapped[float] = mapped_column(Float, nullable=False)
    warning_high: Mapped[float] = mapped_column(Float, nullable=False)
    alarm_type: Mapped[AlarmType] = mapped_column(SQLEnum(AlarmType), default=AlarmType.high)
    alarm_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[ChannelStatus] = mapped_column(SQLEnum(ChannelStatus), default=ChannelStatus.active)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    data_records = relationship(
        "LiquidLevelData",
        back_populates="channel",
        cascade="all, delete-orphan",
    )
    alarms = relationship("Alarm", back_populates="channel", cascade="all, delete-orphan")
