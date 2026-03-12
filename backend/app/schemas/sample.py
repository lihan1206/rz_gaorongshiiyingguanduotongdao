from datetime import datetime

from pydantic import BaseModel, Field

from app.models.liquid_level_data import DataStatus


class SamplePoint(BaseModel):
    channel_id: int
    value: float


class SyncSampleRequest(BaseModel):
    sample_time: datetime | None = None
    temperature: float | None = None
    values: list[SamplePoint] = Field(..., min_length=1)


class SampleRead(BaseModel):
    id: int
    channel_id: int
    value: float
    sample_time: datetime
    temperature: float | None
    status: DataStatus

    class Config:
        from_attributes = True
