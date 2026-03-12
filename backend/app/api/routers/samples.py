from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.liquid_level_data import LiquidLevelData
from app.schemas.sample import SampleRead, SyncSampleRequest
from app.services.sampling import ingest_sync_samples

router = APIRouter(prefix="/samples", tags=["samples"])


@router.post("/sync", response_model=list[SampleRead])
def create_sync_samples(payload: SyncSampleRequest, db: Session = Depends(get_db)):
    try:
        return ingest_sync_samples(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[SampleRead])
def list_samples(
    channel_id: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
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
    start: datetime | None = None,
    end: datetime | None = None,
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
