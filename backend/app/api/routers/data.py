from datetime import datetime
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.liquid_level_data import LiquidLevelData
from app.services.collector import get_collector

router = APIRouter(prefix="/data", tags=["data"])


class LatestDataPoint(BaseModel):
    channel_id: int
    value_a: Optional[float] = None
    value_b: Optional[float] = None
    fused_value: Optional[float] = None
    sample_time: Optional[datetime] = None
    status: str = "unknown"


class LatestDataResponse(BaseModel):
    timestamp: datetime
    channels: Dict[int, LatestDataPoint]
    total: int


@router.get("/latest", response_model=LatestDataResponse)
def get_latest_data(db: Session = Depends(get_db)):
    collector = get_collector()
    realtime_data = collector.get_latest_data() if collector else {}

    channel_ids = list(realtime_data.keys()) if realtime_data else []
    latest_db_data: Dict[int, LiquidLevelData] = {}

    if channel_ids:
        subquery = (
            db.query(
                LiquidLevelData.channel_id,
                db.func.max(LiquidLevelData.sample_time).label("max_time")
            )
            .filter(LiquidLevelData.channel_id.in_(channel_ids))
            .group_by(LiquidLevelData.channel_id)
            .subquery()
        )

        latest_records = (
            db.query(LiquidLevelData)
            .join(
                subquery,
                (LiquidLevelData.channel_id == subquery.c.channel_id) &
                (LiquidLevelData.sample_time == subquery.c.max_time)
            )
            .all()
        )

        for record in latest_records:
            latest_db_data[record.channel_id] = record

    channels: Dict[int, LatestDataPoint] = {}
    for channel_id in channel_ids:
        rt_data = realtime_data.get(channel_id, {})
        db_record = latest_db_data.get(channel_id)

        channels[channel_id] = LatestDataPoint(
            channel_id=channel_id,
            value_a=rt_data.get("value_a"),
            value_b=rt_data.get("value_b"),
            fused_value=db_record.fused_value if db_record else None,
            sample_time=db_record.sample_time if db_record else rt_data.get("timestamp"),
            status=db_record.status.value if db_record else "unknown",
        )

    return LatestDataResponse(
        timestamp=datetime.utcnow(),
        channels=channels,
        total=len(channels),
    )


@router.get("/latest/{channel_id}", response_model=LatestDataPoint)
def get_latest_data_by_channel(channel_id: int, db: Session = Depends(get_db)):
    collector = get_collector()

    realtime_data = {}
    if collector:
        realtime_data = collector.get_latest_data(channel_id).get(channel_id, {})

    latest_record = (
        db.query(LiquidLevelData)
        .filter(LiquidLevelData.channel_id == channel_id)
        .order_by(LiquidLevelData.sample_time.desc())
        .first()
    )

    if not realtime_data and not latest_record:
        raise HTTPException(status_code=404, detail="通道不存在或无数据")

    return LatestDataPoint(
        channel_id=channel_id,
        value_a=realtime_data.get("value_a"),
        value_b=realtime_data.get("value_b"),
        fused_value=latest_record.fused_value if latest_record else None,
        sample_time=latest_record.sample_time if latest_record else realtime_data.get("timestamp"),
        status=latest_record.status.value if latest_record else "unknown",
    )
