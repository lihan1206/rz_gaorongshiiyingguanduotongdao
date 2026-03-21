from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, Enum as SQLEnum, Float, ForeignKey, Index, Integer, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DataStatus(str, Enum):
    normal = "normal"
    warning = "warning"
    error = "error"


class LiquidLevelData(Base):
    __tablename__ = "liquid_level_data"
    __table_args__ = (
        Index("idx_sample_time", "sample_time"),
        Index("idx_channel_sample_time", "channel_id", "sample_time"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("channels.id"), nullable=False)
    value_a: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_b: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fused_value: Mapped[float] = mapped_column(Float, nullable=False)
    sample_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[DataStatus] = mapped_column(SQLEnum(DataStatus), default=DataStatus.normal)

    channel = relationship("Channel", back_populates="data_records")
