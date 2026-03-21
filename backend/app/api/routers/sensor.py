import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.services.sensor_fusion import SensorManager, SensorData
from app.services.sampling import ingest_fused_sensor_data
from app.schemas.sample import SensorDataResponse

router = APIRouter(prefix="/sensor", tags=["sensor"])

sensor_manager = SensorManager(num_channels=8)
_sampling_task = None
_sampling_active = False


@router.get("/read/{channel_id}", response_model=SensorDataResponse)
def read_single_channel(channel_id: int, temperature: float = None):
    """读取单个通道的传感器数据"""
    try:
        sensor_data = sensor_manager.read_channel(channel_id, temperature)
        return sensor_data
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/read-all", response_model=List[SensorDataResponse])
def read_all_channels(temperature: float = None):
    """读取所有通道的传感器数据"""
    sensor_data_list = sensor_manager.read_all_channels(temperature)
    return sensor_data_list


@router.post("/sample-and-store", response_model=List[SensorDataResponse])
def sample_and_store(temperature: float = None, db: Session = Depends(get_db)):
    """采集数据并存储到数据库"""
    sensor_data_list = sensor_manager.read_all_channels(temperature)
    ingest_fused_sensor_data(db, sensor_data_list)
    return sensor_data_list


@router.post("/start-sampling")
async def start_sampling(
    background_tasks: BackgroundTasks,
    frequency_ms: int = 100,
    temperature: float = None,
):
    """启动连续采样"""
    global _sampling_task, _sampling_active

    if _sampling_active:
        raise HTTPException(status_code=400, detail="采样任务已在运行中")

    _sampling_active = True

    async def sampling_loop():
        global _sampling_active
        from app.db.session import SessionLocal

        while _sampling_active:
            try:
                db = SessionLocal()
                sensor_data_list = sensor_manager.read_all_channels(temperature)
                ingest_fused_sensor_data(db, sensor_data_list)
                db.close()
                await asyncio.sleep(frequency_ms / 1000.0)
            except Exception as e:
                print(f"采样过程中发生错误: {e}")
                await asyncio.sleep(1)

    _sampling_task = asyncio.create_task(sampling_loop())
    return {"message": "连续采样已启动", "frequency_ms": frequency_ms}


@router.post("/stop-sampling")
def stop_sampling():
    """停止连续采样"""
    global _sampling_task, _sampling_active

    if not _sampling_active:
        raise HTTPException(status_code=400, detail="没有正在运行的采样任务")

    _sampling_active = False
    if _sampling_task:
        _sampling_task.cancel()
        _sampling_task = None

    return {"message": "连续采样已停止"}


@router.get("/sampling-status")
def get_sampling_status():
    """获取采样状态"""
    return {
        "active": _sampling_active,
        "manager_initialized": sensor_manager is not None,
    }


@router.post("/{channel_id}/start-drift")
def start_drift(channel_id: int, rate: float = -0.1):
    """启动指定通道的漂移模拟"""
    if channel_id not in sensor_manager.simulators:
        raise HTTPException(status_code=404, detail="通道不存在")
    sensor_manager.start_drift(channel_id, rate)
    return {"message": f"通道 {channel_id} 漂移模拟已启动", "rate": rate}


@router.post("/{channel_id}/stop-drift")
def stop_drift(channel_id: int):
    """停止指定通道的漂移模拟"""
    if channel_id not in sensor_manager.simulators:
        raise HTTPException(status_code=404, detail="通道不存在")
    sensor_manager.stop_drift(channel_id)
    return {"message": f"通道 {channel_id} 漂移模拟已停止"}


@router.get("/{channel_id}/status")
def get_channel_status(channel_id: int):
    """获取通道状态"""
    buffer = sensor_manager.get_buffer(channel_id)
    if not buffer:
        raise HTTPException(status_code=404, detail="通道不存在")

    recent_data = buffer.get_recent_data(1)
    latest_value = recent_data[0].fused_value if recent_data else None

    return {
        "channel_id": channel_id,
        "consecutive_warnings": dict(buffer.consecutive_warnings),
        "latest_value": latest_value,
    }
