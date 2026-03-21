from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AlarmLevel(str, Enum):
    low = "low"
    high = "high"
    drift = "drift"


class AlarmType(str, Enum):
    high_threshold = "high_threshold"
    low_threshold = "low_threshold"
    drift = "drift"


class SensorSource(str, Enum):
    capacitive = "capacitive"
    ultrasonic = "ultrasonic"
    fused = "fused"


class Alarm(Base):
    __tablename__ = "alarms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("channels.id"), nullable=False)
    level: Mapped[AlarmLevel] = mapped_column(SQLEnum(AlarmLevel), nullable=False)
    alarm_type: Mapped[AlarmType] = mapped_column(SQLEnum(AlarmType), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    actual_value: Mapped[float] = mapped_column(Float, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sensor_source: Mapped[SensorSource] = mapped_column(SQLEnum(SensorSource), default=SensorSource.fused)

    channel = relationship("Channel", back_populates="alarms")
