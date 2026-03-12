from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.channel import Channel
from app.schemas.channel import ChannelCreate, ChannelRead, ChannelUpdate

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("", response_model=list[ChannelRead])
def list_channels(db: Session = Depends(get_db)):
    return db.query(Channel).order_by(Channel.id.asc()).all()


@router.post("", response_model=ChannelRead, status_code=status.HTTP_201_CREATED)
def create_channel(payload: ChannelCreate, db: Session = Depends(get_db)):
    existing = db.query(Channel).filter(Channel.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="通道名称已存在")

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

    existing = db.query(Channel).filter(Channel.name == payload.name, Channel.id != channel_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="通道名称已存在")

    for field, value in payload.model_dump().items():
        setattr(channel, field, value)

    db.commit()
    db.refresh(channel)
    return channel


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_channel(channel_id: int, db: Session = Depends(get_db)):
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="通道不存在")

    db.delete(channel)
    db.commit()
    return None
