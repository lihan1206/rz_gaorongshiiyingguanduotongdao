from datetime import datetime

from pydantic import BaseModel

from app.models.alarm import AlarmLevel


class AlarmRead(BaseModel):
    id: int
    channel_id: int
    channel_name: str
    level: AlarmLevel
    threshold: float
    actual_value: float
    occurred_at: datetime
    description: str
    resolved: bool
    resolved_at: datetime | None


class AlarmResolveRequest(BaseModel):
    resolved: bool = True
