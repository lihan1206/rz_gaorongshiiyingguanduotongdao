from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.alarm import AlarmLevel, AlarmType, SensorSource


class AlarmRead(BaseModel):
    id: int
    channel_id: int
    channel_name: str
    level: AlarmLevel
    alarm_type: AlarmType
    threshold: float
    actual_value: float
    occurred_at: datetime
    description: str
    resolved: bool
    resolved_at: Optional[datetime]
    sensor_source: SensorSource

    class Config:
        from_attributes = True


class AlarmResolveRequest(BaseModel):
    resolved: bool = True
