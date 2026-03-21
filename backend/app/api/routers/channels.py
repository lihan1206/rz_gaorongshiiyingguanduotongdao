from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.channel import Channel
from app.schemas.channel import ChannelCreate, ChannelRead, ChannelUpdate, ThresholdUpdate
from app.services.sampling import reset_alarm_state

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("", response_model=list)
def list_channels(db: Session = Depends(get_db)):
    return db.query(Channel).order_by(Channel.id.asc()).all()


@router.get("/{channel_id}", response_model=ChannelRead)
def get_channel(channel_id: int, db: Session = Depends(get_db)):
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="通道不存在")
    return channel


@router.post("", response_model=ChannelRead)
def create_channel(payload: ChannelCreate, db: Session = Depends(get_db)):
    channel = Channel(**payload.model_dump())
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


@router.put("/{channel_id}", response_model=ChannelRead)
def update_channel(channel_id: int, payload: ChannelUpdate, db: Session = Depends(get_db)):
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="通道不存在")

    for key, value in payload.model_dump().items():
        setattr(channel, key, value)

    db.commit()
    db.refresh(channel)
    reset_alarm_state(channel_id)
    return channel


@router.post("/thresholds/{channel_id}", response_model=ChannelRead)
def update_threshold(channel_id: int, payload: ThresholdUpdate, db: Session = Depends(get_db)):
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="通道不存在")

    if payload.warning_low is not None:
        channel.warning_low = payload.warning_low
    if payload.warning_high is not None:
        channel.warning_high = payload.warning_high
    if payload.alarm_type is not None:
        channel.alarm_type = payload.alarm_type
    if payload.alarm_enabled is not None:
        channel.alarm_enabled = payload.alarm_enabled

    if channel.warning_low >= channel.warning_high:
        raise HTTPException(status_code=400, detail="报警下限必须小于报警上限")

    db.commit()
    db.refresh(channel)
    reset_alarm_state(channel_id)
    return channel


@router.delete("/{channel_id}")
def delete_channel(channel_id: int, db: Session = Depends(get_db)):
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="通道不存在")

    db.delete(channel)
    db.commit()
    return {"detail": "通道已删除"}
