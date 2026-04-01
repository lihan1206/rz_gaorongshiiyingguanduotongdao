from datetime import datetime
from typing import Optional, List, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.session import get_db
from app.models.liquid_level_data import LiquidLevelData
from app.schemas.sample import SampleRead, SyncSampleRequest, MultiSensorSampleRequest, SensorDataResponse
from app.services.sampling import ingest_sync_samples, ingest_multi_sensor_samples
from app.services.sensor_fusion import SensorManager

router = APIRouter(prefix="/samples", tags=["samples"])

sensor_manager = SensorManager(num_channels=8)


@router.post("/sync", response_model=list[SampleRead])
def create_sync_samples(payload: SyncSampleRequest, db: Session = Depends(get_db)):
    try:
        return ingest_sync_samples(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/multi-sensor", response_model=list[SampleRead])
def create_multi_sensor_samples(payload: MultiSensorSampleRequest, db: Session = Depends(get_db)):
    """接收多传感器数据并进行融合处理"""
    try:
        return ingest_multi_sensor_samples(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=List[SampleRead])
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
        yield "id,channel_id,value,sample_time,temperature,status\n"
        for row in records:
            yield (
                f"{row.id},{row.channel_id},{row.value},"
                f"{row.sample_time.isoformat()},{row.temperature or ''},{row.status.value}\n"
            )

    filename = f"liquid_level_report_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.csv"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(iter_csv(), media_type="text/csv", headers=headers)


@router.get("/latest", response_model=Dict[int, SampleRead])
def get_latest_data(
    channel_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """获取最新数据 - 支持单通道或所有通道"""
    if channel_id is not None:
        latest = db.query(LiquidLevelData).filter(
            LiquidLevelData.channel_id == channel_id
        ).order_by(LiquidLevelData.sample_time.desc()).first()
        
        if not latest:
            raise HTTPException(status_code=404, detail=f"通道 {channel_id} 无数据")
        return {channel_id: latest}
    
    subquery = db.query(
        LiquidLevelData.channel_id,
        func.max(LiquidLevelData.sample_time).label('max_time')
    ).group_by(LiquidLevelData.channel_id).subquery()
    
    latest_records = db.query(LiquidLevelData).join(
        subquery,
        (LiquidLevelData.channel_id == subquery.c.channel_id) &
        (LiquidLevelData.sample_time == subquery.c.max_time)
    ).all()
    
    return {record.channel_id: record for record in latest_records}


@router.get("/simulate", response_model=List[SensorDataResponse])
def simulate_sensor_reading(
    channel_id: Optional[int] = None,
    temperature: Optional[float] = 25.0,
):
    """模拟传感器读数 - 用于测试"""
    if channel_id is not None:
        try:
            data = sensor_manager.read_channel(channel_id, temperature)
            return [data]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    data_list = sensor_manager.read_all_channels(temperature)
    return data_list


@router.get("/statistics", response_model=Dict)
def get_statistics(
    channel_id: Optional[int] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    """获取统计数据"""
    query = db.query(
        LiquidLevelData.channel_id,
        func.avg(LiquidLevelData.value).label('avg_value'),
        func.max(LiquidLevelData.value).label('max_value'),
        func.min(LiquidLevelData.value).label('min_value'),
        func.count(LiquidLevelData.id).label('sample_count')
    )
    
    if channel_id is not None:
        query = query.filter(LiquidLevelData.channel_id == channel_id)
    if start is not None:
        query = query.filter(LiquidLevelData.sample_time >= start)
    if end is not None:
        query = query.filter(LiquidLevelData.sample_time <= end)
    
    stats = query.group_by(LiquidLevelData.channel_id).all()
    
    result = {}
    for stat in stats:
        result[stat.channel_id] = {
            "avg_value": round(float(stat.avg_value or 0), 3),
            "max_value": round(float(stat.max_value or 0), 3),
            "min_value": round(float(stat.min_value or 0), 3),
            "sample_count": stat.sample_count
        }
    return result
