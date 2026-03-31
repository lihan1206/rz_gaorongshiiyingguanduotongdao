import logging
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.api.routers import alarms, auth, channels, dashboard, config as config_router, sensor
from app.config import AppConfig, settings, ConfigError
from app.database import DatabaseManager, ConnectionError, QueryError
from app.sensor import SensorManager, SensorError, SerialPortError
from app.fusion import FusionManager, FusionError
from app.alarm import AlarmDetector, AlarmError, ChannelAlarmConfig
from app.core.logging_config import setup_logging
from app.db.base import Base
from app.db.seed import run_seed
from app.models.alarm import Alarm as AlarmModel
from app.models.channel import Channel
from app.models.liquid_level_data import LiquidLevelData
from app.schemas.sample import SyncSampleRequest, MultiSensorSampleRequest

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, version="1.0.0")

origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
if not origins:
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(channels.router, prefix="/api")
app.include_router(alarms.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(config_router.router, prefix="/api")
app.include_router(sensor.router, prefix="/api")

try:
    db_manager = DatabaseManager(settings.sqlalchemy_database_uri)
    db_manager.test_connection()
except ConnectionError as e:
    logger.error(f"数据库初始化失败: {e}")
    raise
except Exception as e:
    logger.error(f"未知错误: {e}")
    raise

try:
    sampling_settings = AppConfig.get_sampling_settings()
    sensor_manager = SensorManager(
        num_channels=sampling_settings.get("max_channels", 8)
    )
except SensorError as e:
    logger.error(f"传感器管理器初始化失败: {e}")
    raise

try:
    sensor_weights = AppConfig.get_sensor_weights()
    fusion_manager = FusionManager(
        sensor_manager=sensor_manager,
        weights=sensor_weights,
        use_kalman=True,
    )
except FusionError as e:
    logger.error(f"数据融合管理器初始化失败: {e}")
    raise

try:
    alarm_settings = AppConfig.get_alarm_settings()
    alarm_detector = AlarmDetector(alarm_settings=alarm_settings)
except AlarmError as e:
    logger.error(f"报警检测器初始化失败: {e}")
    raise


def get_db():
    try:
        with db_manager.get_session() as session:
            yield session
    except ConnectionError as e:
        logger.error(f"数据库连接失败: {e}")
        raise HTTPException(status_code=500, detail=f"数据库连接失败: {e}")
    except QueryError as e:
        logger.error(f"数据库查询失败: {e}")
        raise HTTPException(status_code=500, detail=f"数据库查询失败: {e}")


@app.on_event("startup")
def startup_event() -> None:
    try:
        logger.info("准备初始化数据库表结构")
        Base.metadata.create_all(bind=db_manager.engine)
        with db_manager.get_session() as db:
            run_seed(db)
        logger.info("系统启动完成")
    except Exception as e:
        logger.error(f"系统启动失败: {e}")
        raise


def get_channel_config(db: Session, channel_id: int) -> ChannelAlarmConfig:
    try:
        channel = db.query(Channel).filter(Channel.id == channel_id).first()
        if channel:
            return ChannelAlarmConfig(
                warning_low=channel.warning_low,
                warning_high=channel.warning_high,
                drift_threshold=channel.drift_threshold,
                drift_time_window=channel.drift_time_window,
                enabled_alarms=channel.get_enabled_alarm_types(),
            )
        else:
            threshold_config = AppConfig.get_threshold(channel_id)
            return ChannelAlarmConfig(
                warning_low=threshold_config.get("warning_low", 10.0),
                warning_high=threshold_config.get("warning_high", 90.0),
                drift_threshold=threshold_config.get("drift_threshold", 0.5),
                drift_time_window=threshold_config.get("drift_time_window", 5),
            )
    except ConfigError as e:
        logger.error(f"获取通道配置失败: {e}")
        raise
    except Exception as e:
        logger.error(f"获取通道配置发生未知错误: {e}")
        raise


def process_sensor_data(
    sensor_data_list: List,
    db: Session,
) -> List[LiquidLevelData]:
    try:
        records: List[LiquidLevelData] = []
        channel_ids = [data.channel_id for data in sensor_data_list]
        channels = db.query(Channel).filter(Channel.id.in_(channel_ids)).all()
        channel_map = {c.id: c for c in channels}

        for sensor_data in sensor_data_list:
            try:
                channel = channel_map.get(sensor_data.channel_id)
                if not channel:
                    logger.warning(f"通道 {sensor_data.channel_id} 不存在，跳过")
                    continue

                actual_value = sensor_data.fused_value + channel.calibration_offset
                sensor_data.fused_value = actual_value

                db_data = LiquidLevelData(
                    channel_id=sensor_data.channel_id,
                    value=actual_value,
                    capacitive_value=sensor_data.capacitive_value,
                    ultrasonic_value=sensor_data.ultrasonic_value,
                    fused_value=actual_value,
                    sample_time=sensor_data.timestamp,
                    temperature=sensor_data.temperature,
                    status="normal",
                    sensor_source="fused",
                )
                db.add(db_data)
                records.append(db_data)

                if channel.alarm_enabled:
                    if sensor_data.channel_id not in alarm_detector.channel_configs:
                        channel_config = get_channel_config(db, sensor_data.channel_id)
                        alarm_detector.configure_channel(sensor_data.channel_id, channel_config)

                    alarms = alarm_detector.process_value(
                        channel_id=sensor_data.channel_id,
                        value=actual_value,
                        timestamp=sensor_data.timestamp,
                        channel_name=channel.name,
                        unit=channel.unit,
                    )

                    for alarm in alarms:
                        alarm_model = AlarmModel(
                            channel_id=alarm.channel_id,
                            level=alarm.level.value if hasattr(alarm.level, 'value') else alarm.level,
                            alarm_type=alarm.alarm_type.value if hasattr(alarm.alarm_type, 'value') else alarm.alarm_type,
                            threshold=alarm.threshold,
                            actual_value=alarm.actual_value,
                            occurred_at=alarm.occurred_at,
                            description=alarm.description,
                            sensor_source=alarm.sensor_source.value if hasattr(alarm.sensor_source, 'value') else alarm.sensor_source,
                        )
                        db.add(alarm_model)

            except AlarmError as e:
                logger.error(f"处理通道 {sensor_data.channel_id} 报警时出错: {e}")
                continue
            except Exception as e:
                logger.error(f"处理通道 {sensor_data.channel_id} 数据时发生未知错误: {e}")
                continue

        db.commit()
        for record in records:
            db.refresh(record)
        return records

    except Exception as e:
        logger.error(f"处理传感器数据失败: {e}")
        db.rollback()
        raise


@app.post("/api/samples/sync", summary="同步采集样本数据")
def ingest_sync_samples(
    payload: SyncSampleRequest,
    db: Session = Depends(get_db),
):
    try:
        sample_time = payload.sample_time or datetime.utcnow()
        point_map = {point.channel_id: point.value for point in payload.values}
        channel_ids = list(point_map.keys())
        channels = db.query(Channel).filter(Channel.id.in_(channel_ids)).all()

        if len(channels) != len(point_map):
            missing_ids = sorted(set(point_map.keys()) - {channel.id for channel in channels})
            raise HTTPException(status_code=400, detail=f"通道不存在: {missing_ids}")

        from app.sensor import SensorData as InternalSensorData
        sensor_data_list = []
        for channel in channels:
            value = point_map[channel.id]
            sensor_data = InternalSensorData(
                channel_id=channel.id,
                capacitive_value=value,
                ultrasonic_value=value,
                fused_value=value,
                temperature=payload.temperature,
                timestamp=sample_time,
            )
            sensor_data_list.append(sensor_data)

        records = process_sensor_data(sensor_data_list, db)
        return {"message": "数据上传成功", "count": len(records), "data": records}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理同步采样数据失败: {e}")
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


@app.post("/api/samples/multi-sensor", summary="多传感器数据采集")
def ingest_multi_sensor_samples(
    payload: MultiSensorSampleRequest,
    db: Session = Depends(get_db),
):
    try:
        sample_time = payload.sample_time or datetime.utcnow()
        channel_data = {}

        for point in payload.values:
            if point.channel_id not in channel_data:
                channel_data[point.channel_id] = {
                    "capacitive": None,
                    "ultrasonic": None,
                }
            channel_data[point.channel_id][point.sensor_type] = point.value

        channel_ids = list(channel_data.keys())
        channels = db.query(Channel).filter(Channel.id.in_(channel_ids)).all()

        if len(channels) != len(channel_data):
            missing_ids = sorted(set(channel_data.keys()) - {channel.id for channel in channels})
            raise HTTPException(status_code=400, detail=f"通道不存在: {missing_ids}")

        from app.sensor import SensorData as InternalSensorData
        sensor_data_list = []
        for channel in channels:
            data = channel_data[channel.id]
            cap_value = data.get("capacitive") or data.get("ultrasonic") or 0.0
            ult_value = data.get("ultrasonic") or data.get("capacitive") or 0.0

            sensor_data = InternalSensorData(
                channel_id=channel.id,
                capacitive_value=cap_value,
                ultrasonic_value=ult_value,
                fused_value=0.0,
                temperature=payload.temperature,
                timestamp=sample_time,
            )
            sensor_data_list.append(sensor_data)

        fused_data = fusion_manager.process_batch(sensor_data_list)
        records = process_sensor_data(fused_data, db)

        return {"message": "多传感器数据上传成功", "count": len(records), "data": records}

    except HTTPException:
        raise
    except FusionError as e:
        logger.error(f"数据融合失败: {e}")
        raise HTTPException(status_code=500, detail=f"数据融合失败: {str(e)}")
    except Exception as e:
        logger.error(f"处理多传感器数据失败: {e}")
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


@app.get("/api/config/reload", summary="重新加载配置")
def reload_config():
    try:
        AppConfig.reload_all()
        return {"message": "配置已重新加载", "info": AppConfig.get_config_info()}
    except ConfigError as e:
        logger.error(f"重新加载配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"重新加载配置失败: {str(e)}")


@app.get("/api/config/info", summary="获取配置信息")
def get_config_info():
    return AppConfig.get_config_info()


@app.get("/", summary="根路径")
def root():
    return {"message": "高融石英管多通道液位同步检测系统后端服务已启动"}


@app.get("/api/health", summary="健康检查")
def health_check():
    try:
        db_status = db_manager.test_connection()
        return {
            "status": "healthy",
            "database": "connected" if db_status else "disconnected",
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }
