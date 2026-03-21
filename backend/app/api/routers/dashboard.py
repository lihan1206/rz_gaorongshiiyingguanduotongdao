from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.alarm import Alarm
from app.models.channel import Channel, ChannelStatus
from app.models.liquid_level_data import LiquidLevelData
from app.schemas.dashboard import ChannelLatest, DashboardSummary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(db: Session = Depends(get_db)):
    total_channels = db.query(func.count(Channel.id)).scalar() or 0
    active_channels = (
        db.query(func.count(Channel.id))
        .filter(Channel.status == ChannelStatus.active)
        .scalar()
        or 0
    )
    total_samples = db.query(func.count(LiquidLevelData.id)).scalar() or 0
    unresolved_alarms = (
        db.query(func.count(Alarm.id)).filter(Alarm.resolved == False).scalar() or 0
    )

    subq = (
        db.query(
            LiquidLevelData.channel_id,
            func.max(LiquidLevelData.sample_time).label("max_time"),
        )
        .group_by(LiquidLevelData.channel_id)
        .subquery()
    )

    latest_rows = (
        db.query(LiquidLevelData, Channel.name, Channel.status)
        .join(subq, (LiquidLevelData.channel_id == subq.c.channel_id) & (LiquidLevelData.sample_time == subq.c.max_time))
        .join(Channel, Channel.id == LiquidLevelData.channel_id)
        .all()
    )

    latest_by_channel = [
        ChannelLatest(
            channel_id=row.LiquidLevelData.channel_id,
            channel_name=row.name,
            channel_status=row.status,
            latest_value_a=row.LiquidLevelData.value_a,
            latest_value_b=row.LiquidLevelData.value_b,
            latest_value=row.LiquidLevelData.fused_value,
            latest_time=row.LiquidLevelData.sample_time,
            latest_status=row.LiquidLevelData.status,
        )
        for row in latest_rows
    ]

    return DashboardSummary(
        total_channels=total_channels,
        active_channels=active_channels,
        total_samples=total_samples,
        unresolved_alarms=unresolved_alarms,
        latest_by_channel=latest_by_channel,
    )
