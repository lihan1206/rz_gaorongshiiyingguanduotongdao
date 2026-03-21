from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field

from app.models.liquid_level_data import DataStatus, SensorSource


class SamplePoint(BaseModel):
    channel_id: int
    value: float


class MultiSensorSamplePoint(BaseModel):
    channel_id: int
    sensor_type: str
    value: float


class SyncSampleRequest(BaseModel):
    sample_time: Optional[datetime] = None
    temperature: Optional[float] = None
    values: List[SamplePoint] = Field(..., min_length=1)


class MultiSensorSampleRequest(BaseModel):
    sample_time: Optional[datetime] = None
    temperature: Optional[float] = None
    values: List[MultiSensorSamplePoint] = Field(..., min_length=1)


class SampleRead(BaseModel):
    id: int
    channel_id: int
    value: float
    capacitive_value: float
    ultrasonic_value: float
    fused_value: float
    sample_time: datetime
    temperature: Optional[float]
    status: DataStatus
    sensor_source: SensorSource

    class Config:
        from_attributes = True


class SensorDataResponse(BaseModel):
    channel_id: int
    capacitive_value: float
    ultrasonic_value: float
    fused_value: float
    temperature: Optional[float]
    timestamp: datetime
