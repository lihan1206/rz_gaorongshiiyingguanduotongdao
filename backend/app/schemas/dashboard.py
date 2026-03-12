from datetime import datetime

from pydantic import BaseModel

from app.models.channel import ChannelStatus
from app.models.liquid_level_data import DataStatus


class ChannelLatest(BaseModel):
    channel_id: int
    channel_name: str
    channel_status: ChannelStatus
    latest_value: float | None
    latest_time: datetime | None
    latest_status: DataStatus | None


class DashboardSummary(BaseModel):
    total_channels: int
    active_channels: int
    total_samples: int
    unresolved_alarms: int
    latest_by_channel: list[ChannelLatest]
