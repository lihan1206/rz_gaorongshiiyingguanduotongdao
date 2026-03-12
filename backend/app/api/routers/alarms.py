from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.alarm import Alarm
from app.models.channel import Channel
from app.schemas.alarm import AlarmRead

router = APIRouter(prefix="/alarms", tags=["alarms"])


@router.get("", response_model=list[AlarmRead])
def list_alarms(resolved: bool | None = None, db: Session = Depends(get_db)):
    query = db.query(Alarm, Channel.name).join(Channel, Channel.id == Alarm.channel_id)
    if resolved is not None:
        query = query.filter(Alarm.resolved == resolved)

    rows = query.order_by(Alarm.occurred_at.desc()).limit(500).all()
    return [
        AlarmRead(
            id=alarm.id,
            channel_id=alarm.channel_id,
            channel_name=channel_name,
            level=alarm.level,
            threshold=alarm.threshold,
            actual_value=alarm.actual_value,
            occurred_at=alarm.occurred_at,
            description=alarm.description,
            resolved=alarm.resolved,
            resolved_at=alarm.resolved_at,
        )
        for alarm, channel_name in rows
    ]


@router.post("/{alarm_id}/resolve", response_model=AlarmRead)
def resolve_alarm(alarm_id: int, db: Session = Depends(get_db)):
    alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
    if not alarm:
        raise HTTPException(status_code=404, detail="报警记录不存在")

    alarm.resolved = True
    alarm.resolved_at = datetime.utcnow()
    db.commit()

    channel_name = db.query(Channel.name).filter(Channel.id == alarm.channel_id).scalar() or "未知通道"
    return AlarmRead(
        id=alarm.id,
        channel_id=alarm.channel_id,
        channel_name=channel_name,
        level=alarm.level,
        threshold=alarm.threshold,
        actual_value=alarm.actual_value,
        occurred_at=alarm.occurred_at,
        description=alarm.description,
        resolved=alarm.resolved,
        resolved_at=alarm.resolved_at,
    )
