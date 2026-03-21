from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class SensorWeightsUpdate(BaseModel):
    capacitive: float = Field(..., ge=0.0, le=1.0)
    ultrasonic: float = Field(..., ge=0.0, le=1.0)


class ThresholdUpdate(BaseModel):
    warning_low: Optional[float] = Field(None, ge=0.0)
    warning_high: Optional[float] = Field(None, ge=0.0)
    drift_threshold: Optional[float] = Field(None, ge=0.0)
    drift_time_window: Optional[int] = Field(None, ge=1)
    enabled_alarm_types: Optional[str] = Field(None, max_length=100)


class ChannelThresholdUpdate(BaseModel):
    warning_low: Optional[float] = Field(None, ge=0.0)
    warning_high: Optional[float] = Field(None, ge=0.0)
    drift_threshold: Optional[float] = Field(None, ge=0.0)
    drift_time_window: Optional[int] = Field(None, ge=1)
    enabled_alarm_types: Optional[str] = Field(None, max_length=100)


class ConfigResponse(BaseModel):
    sensor_weights: Dict[str, float]
    default_thresholds: Dict[str, Any]
    alarm_settings: Dict[str, Any]
    sampling: Dict[str, Any]


class SensorWeightsResponse(BaseModel):
    capacitive: float
    ultrasonic: float
    message: Optional[str] = None


class ThresholdResponse(BaseModel):
    channel_id: int
    warning_low: float
    warning_high: float
    drift_threshold: float
    drift_time_window: int
    enabled_alarm_types: str
    message: Optional[str] = None
