from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.channel import ChannelStatus
from app.models.liquid_level_data import DataStatus


class ChannelLatest(BaseModel):
    channel_id: int
    channel_name: str
    channel_status: ChannelStatus
    latest_value_a: Optional[float]
    latest_value_b: Optional[float]
    latest_value: Optional[float]
    latest_time: Optional[datetime]
    latest_status: Optional[DataStatus]


class DashboardSummary(BaseModel):
    total_channels: int
    active_channels: int
    total_samples: int
    unresolved_alarms: int
    latest_by_channel: list
