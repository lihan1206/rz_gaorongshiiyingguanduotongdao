from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.config import AppConfig
from app.models.channel import Channel
from app.schemas.config import (
    ConfigResponse,
    SensorWeightsUpdate,
    SensorWeightsResponse,
    ChannelThresholdUpdate,
    ThresholdResponse,
)

router = APIRouter(prefix="/config", tags=["config"])


@router.get("", response_model=ConfigResponse)
def get_config():
    """获取系统配置"""
    return {
        "sensor_weights": AppConfig.get_sensor_weights(),
        "default_thresholds": AppConfig.get("default_thresholds", {}),
        "alarm_settings": AppConfig.get_alarm_settings(),
        "sampling": AppConfig.get_sampling_settings(),
    }


@router.put("/sensor-weights", response_model=SensorWeightsResponse)
def update_sensor_weights(payload: SensorWeightsUpdate):
    """更新传感器权重配置"""
    try:
        AppConfig.set_sensor_weights(payload.capacitive, payload.ultrasonic)
        return {
            "capacitive": payload.capacitive,
            "ultrasonic": payload.ultrasonic,
            "message": "传感器权重配置已更新",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sensor-weights", response_model=SensorWeightsResponse)
def get_sensor_weights():
    """获取传感器权重配置"""
    weights = AppConfig.get_sensor_weights()
    return {
        "capacitive": weights.get("capacitive", 0.6),
        "ultrasonic": weights.get("ultrasonic", 0.4),
    }


@router.get("/thresholds/{channel_id}", response_model=ThresholdResponse)
def get_channel_thresholds(channel_id: int, db: Session = Depends(get_db)):
    """获取指定通道的报警阈值配置"""
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="通道不存在")

    return {
        "channel_id": channel.id,
        "warning_low": channel.warning_low,
        "warning_high": channel.warning_high,
        "drift_threshold": channel.drift_threshold,
        "drift_time_window": channel.drift_time_window,
        "enabled_alarm_types": channel.enabled_alarm_types,
    }


@router.put("/thresholds/{channel_id}", response_model=ThresholdResponse)
def update_channel_thresholds(
    channel_id: int,
    payload: ChannelThresholdUpdate,
    db: Session = Depends(get_db),
):
    """更新指定通道的报警阈值配置（支持热更新）"""
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="通道不存在")

    update_data = payload.model_dump(exclude_unset=True)

    if "warning_low" in update_data and "warning_high" in update_data:
        if update_data["warning_low"] >= update_data["warning_high"]:
            raise HTTPException(status_code=400, detail="报警下限必须小于报警上限")

    for field, value in update_data.items():
        if hasattr(channel, field):
            setattr(channel, field, value)

    db.commit()
    db.refresh(channel)

    return {
        "channel_id": channel.id,
        "warning_low": channel.warning_low,
        "warning_high": channel.warning_high,
        "drift_threshold": channel.drift_threshold,
        "drift_time_window": channel.drift_time_window,
        "enabled_alarm_types": channel.enabled_alarm_types,
        "message": "通道阈值配置已更新",
    }


@router.post("/thresholds/{channel_id}/reset")
def reset_channel_thresholds(channel_id: int, db: Session = Depends(get_db)):
    """重置通道阈值为默认值"""
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="通道不存在")

    default_thresholds = AppConfig.get("default_thresholds", {})
    channel.warning_low = default_thresholds.get("warning_low", 10.0)
    channel.warning_high = default_thresholds.get("warning_high", 90.0)
    channel.drift_threshold = default_thresholds.get("drift_threshold", 0.5)
    channel.drift_time_window = default_thresholds.get("drift_time_window", 5)
    channel.enabled_alarm_types = "high,low,drift"

    db.commit()

    return {"message": "通道阈值已重置为默认值"}


@router.get("/alarm-settings")
def get_alarm_settings():
    """获取全局报警设置"""
    return AppConfig.get_alarm_settings()


@router.put("/reload")
def reload_config():
    """重新加载配置文件"""
    AppConfig.load_config()
    return {"message": "配置文件已重新加载"}
