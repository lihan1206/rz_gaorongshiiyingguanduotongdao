from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.liquid_level_data import DataStatus


class DualSensorPoint(BaseModel):
    channel_id: int
    value_a: Optional[float] = None
    value_b: Optional[float] = None


class SyncSampleRequest(BaseModel):
    sample_time: Optional[datetime] = None
    temperature: Optional[float] = None
    values: list = Field(..., min_length=1)


class SampleRead(BaseModel):
    id: int
    channel_id: int
    value_a: Optional[float]
    value_b: Optional[float]
    fused_value: float
    sample_time: datetime
    temperature: Optional[float]
    status: DataStatus

    class Config:
        from_attributes = True
