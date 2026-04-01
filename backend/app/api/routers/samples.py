from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.liquid_level_data import LiquidLevelData
from app.schemas.sample import SampleRead, SyncSampleRequest
from app.services.sampling import ingest_sync_samples
from app.services.collector import get_collector

router = APIRouter(prefix="/samples", tags=["samples"])


class LatestDataResponse(BaseModel):
    channel_id: int
    value_a: Optional[float] = None
    value_b: Optional[float] = None
    timestamp: Optional[datetime] = None
    status_a: str = "unknown"
    status_b: str = "unknown"


class AllLatestDataResponse(BaseModel):
    data: Dict[int, LatestDataResponse]
    total_channels: int


@router.post("/sync", response_model=list)
def create_sync_samples(payload: SyncSampleRequest, db: Session = Depends(get_db)):
    try:
        return ingest_sync_samples(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list)
def list_samples(
    channel_id: Optional[int] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = Query(default=300, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    query = db.query(LiquidLevelData)
    if channel_id is not None:
        query = query.filter(LiquidLevelData.channel_id == channel_id)
    if start is not None:
        query = query.filter(LiquidLevelData.sample_time >= start)
    if end is not None:
        query = query.filter(LiquidLevelData.sample_time <= end)

    return query.order_by(LiquidLevelData.sample_time.desc()).limit(limit).all()[::-1]


@router.get("/export")
def export_samples_csv(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    query = db.query(LiquidLevelData)
    if start is not None:
        query = query.filter(LiquidLevelData.sample_time >= start)
    if end is not None:
        query = query.filter(LiquidLevelData.sample_time <= end)

    records = query.order_by(LiquidLevelData.sample_time.asc()).all()

    def iter_csv():
        yield "id,channel_id,value_a,value_b,fused_value,sample_time,temperature,status\n"
        for row in records:
            value_a_str = str(row.value_a) if row.value_a is not None else ""
            value_b_str = str(row.value_b) if row.value_b is not None else ""
            yield (
                f"{row.id},{row.channel_id},{value_a_str},{value_b_str},"
                f"{row.fused_value},{row.sample_time.isoformat()},"
                f"{row.temperature or ''},{row.status.value}\n"
            )

    filename = f"liquid_level_report_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.csv"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(iter_csv(), media_type="text/csv", headers=headers)


@router.get("/latest", response_model=AllLatestDataResponse)
def get_latest_data():
    collector = get_collector()
    if not collector:
        return AllLatestDataResponse(data={}, total_channels=0)

    raw_data = collector.get_latest_data()
    formatted_data: Dict[int, LatestDataResponse] = {}

    for channel_id, channel_data in raw_data.items():
        formatted_data[channel_id] = LatestDataResponse(
            channel_id=channel_id,
            value_a=channel_data.get("value_a"),
            value_b=channel_data.get("value_b"),
            timestamp=channel_data.get("timestamp"),
            status_a=channel_data.get("status_a", "unknown"),
            status_b=channel_data.get("status_b", "unknown"),
        )

    return AllLatestDataResponse(
        data=formatted_data,
        total_channels=len(formatted_data),
    )


@router.get("/latest/{channel_id}", response_model=LatestDataResponse)
def get_latest_data_by_channel(channel_id: int):
    collector = get_collector()
    if not collector:
        raise HTTPException(status_code=503, detail="采集服务未启动")

    raw_data = collector.get_latest_data(channel_id)
    if channel_id not in raw_data:
        raise HTTPException(status_code=404, detail="通道不存在或无数据")

    channel_data = raw_data[channel_id]
    return LatestDataResponse(
        channel_id=channel_id,
        value_a=channel_data.get("value_a"),
        value_b=channel_data.get("value_b"),
        timestamp=channel_data.get("timestamp"),
        status_a=channel_data.get("status_a", "unknown"),
        status_b=channel_data.get("status_b", "unknown"),
    )
