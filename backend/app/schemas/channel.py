from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.channel import ChannelStatus, SensorType


class ChannelBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    sensor_type: SensorType
    range_min: float
    range_max: float
    unit: str = Field(default="mm", min_length=1, max_length=10)
    calibration_offset: float = 0
    warning_low: float
    warning_high: float
    drift_threshold: float = 0.5
    drift_time_window: int = 5
    alarm_enabled: bool = True
    enabled_alarm_types: str = "high,low,drift"
    status: ChannelStatus = ChannelStatus.active

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.range_min >= self.range_max:
            raise ValueError("量程下限必须小于量程上限")
        if not (self.range_min <= self.warning_low <= self.warning_high <= self.range_max):
            raise ValueError("报警阈值必须位于量程范围内")
        return self


class ChannelCreate(ChannelBase):
    pass


class ChannelUpdate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    sensor_type: SensorType
    range_min: float
    range_max: float
    unit: str = Field(default="mm", min_length=1, max_length=10)
    calibration_offset: float = 0
    warning_low: float
    warning_high: float
    drift_threshold: float = 0.5
    drift_time_window: int = 5
    alarm_enabled: bool = True
    enabled_alarm_types: str = "high,low,drift"
    status: ChannelStatus = ChannelStatus.active

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.range_min >= self.range_max:
            raise ValueError("量程下限必须小于量程上限")
        if not (self.range_min <= self.warning_low <= self.warning_high <= self.range_max):
            raise ValueError("报警阈值必须位于量程范围内")
        return self


class ChannelRead(ChannelBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
