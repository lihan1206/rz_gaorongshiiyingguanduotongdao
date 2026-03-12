from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.alarm import Alarm
from app.models.channel import Channel, ChannelStatus
from app.models.liquid_level_data import LiquidLevelData
from app.schemas.dashboard import ChannelLatest, DashboardSummary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(db: Session = Depends(get_db)):
    channels = db.query(Channel).order_by(Channel.id.asc()).all()
    total_channels = len(channels)
    active_channels = len([channel for channel in channels if channel.status == ChannelStatus.active])
    total_samples = db.query(LiquidLevelData).count()
    unresolved_alarms = db.query(Alarm).filter(Alarm.resolved.is_(False)).count()

    latest_by_channel: list[ChannelLatest] = []
    for channel in channels:
        latest = (
            db.query(LiquidLevelData)
            .filter(LiquidLevelData.channel_id == channel.id)
            .order_by(LiquidLevelData.sample_time.desc())
            .first()
        )

        latest_by_channel.append(
            ChannelLatest(
                channel_id=channel.id,
                channel_name=channel.name,
                channel_status=channel.status,
                latest_value=latest.value if latest else None,
                latest_time=latest.sample_time if latest else None,
                latest_status=latest.status if latest else None,
            )
        )

    return DashboardSummary(
        total_channels=total_channels,
        active_channels=active_channels,
        total_samples=total_samples,
        unresolved_alarms=unresolved_alarms,
        latest_by_channel=latest_by_channel,
    )
