from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.alarm import AlarmLevel


class AlarmRead(BaseModel):
    id: int
    channel_id: int
    channel_name: str
    level: AlarmLevel
    threshold: float
    actual_value: float
    value_a: Optional[float]
    value_b: Optional[float]
    sensor_source: str
    occurred_at: datetime
    description: str
    resolved: bool
    resolved_at: Optional[datetime]

    class Config:
        from_attributes = True


class AlarmResolveRequest(BaseModel):
    resolved: bool = True
