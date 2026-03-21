from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.models.channel import AlarmType, ChannelStatus, SensorType


class ChannelBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    sensor_type_a: SensorType = Field(default=SensorType.capacitive)
    sensor_type_b: Optional[SensorType] = Field(default=SensorType.ultrasonic)
    range_min: float
    range_max: float
    unit: str = Field(default="mm", min_length=1, max_length=10)
    calibration_offset_a: float = 0
    calibration_offset_b: float = 0
    fusion_weight_a: float = Field(default=0.5, ge=0, le=1)
    fusion_weight_b: float = Field(default=0.5, ge=0, le=1)
    warning_low: float
    warning_high: float
    alarm_type: AlarmType = Field(default=AlarmType.high)
    alarm_enabled: bool = True
    status: ChannelStatus = ChannelStatus.active

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.range_min >= self.range_max:
            raise ValueError("量程下限必须小于量程上限")
        if not (self.range_min <= self.warning_low <= self.warning_high <= self.range_max):
            raise ValueError("报警阈值必须位于量程范围内")
        total_weight = self.fusion_weight_a + self.fusion_weight_b
        if abs(total_weight - 1.0) > 0.001:
            raise ValueError("融合权重之和必须为1")
        return self


class ChannelCreate(ChannelBase):
    pass


class ChannelUpdate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    sensor_type_a: SensorType
    sensor_type_b: Optional[SensorType] = None
    range_min: float
    range_max: float
    unit: str = Field(default="mm", min_length=1, max_length=10)
    calibration_offset_a: float = 0
    calibration_offset_b: float = 0
    fusion_weight_a: float = Field(default=0.5, ge=0, le=1)
    fusion_weight_b: float = Field(default=0.5, ge=0, le=1)
    warning_low: float
    warning_high: float
    alarm_type: AlarmType = Field(default=AlarmType.high)
    alarm_enabled: bool = True
    status: ChannelStatus = ChannelStatus.active

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.range_min >= self.range_max:
            raise ValueError("量程下限必须小于量程上限")
        if not (self.range_min <= self.warning_low <= self.warning_high <= self.range_max):
            raise ValueError("报警阈值必须位于量程范围内")
        total_weight = self.fusion_weight_a + self.fusion_weight_b
        if abs(total_weight - 1.0) > 0.001:
            raise ValueError("融合权重之和必须为1")
        return self


class ThresholdUpdate(BaseModel):
    warning_low: Optional[float] = None
    warning_high: Optional[float] = None
    alarm_type: Optional[AlarmType] = None
    alarm_enabled: Optional[bool] = None


class ChannelRead(ChannelBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
