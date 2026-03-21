from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SensorType(str, Enum):
    capacitive = "capacitive"
    ultrasonic = "ultrasonic"
    laser = "laser"
    hybrid = "hybrid"


class ChannelStatus(str, Enum):
    active = "active"
    inactive = "inactive"


class AlarmType(str, Enum):
    high = "high"
    low = "low"
    drift = "drift"


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    sensor_type: Mapped[SensorType] = mapped_column(SQLEnum(SensorType), nullable=False)
    range_min: Mapped[float] = mapped_column(Float, nullable=False)
    range_max: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(10), default="mm")
    calibration_offset: Mapped[float] = mapped_column(Float, default=0.0)
    warning_low: Mapped[float] = mapped_column(Float, nullable=False)
    warning_high: Mapped[float] = mapped_column(Float, nullable=False)
    drift_threshold: Mapped[float] = mapped_column(Float, default=0.5)
    drift_time_window: Mapped[int] = mapped_column(Integer, default=5)
    alarm_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled_alarm_types: Mapped[str] = mapped_column(String(100), default="high,low,drift")
    status: Mapped[ChannelStatus] = mapped_column(SQLEnum(ChannelStatus), default=ChannelStatus.active)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    data_records = relationship(
        "LiquidLevelData",
        back_populates="channel",
        cascade="all, delete-orphan",
    )
    alarms = relationship("Alarm", back_populates="channel", cascade="all, delete-orphan")

    def get_enabled_alarm_types(self) -> list[AlarmType]:
        return [AlarmType(t.strip()) for t in self.enabled_alarm_types.split(",") if t.strip()]
