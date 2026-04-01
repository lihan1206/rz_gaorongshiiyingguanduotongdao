import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.channel import Channel, ChannelStatus
from app.models.liquid_level_data import DataStatus, LiquidLevelData
from app.schemas.sample import SyncSampleRequest, SamplePoint
from app.services.config_manager import get_config_manager
from app.services.fusion import DataStatus as FusionDataStatus
from app.services.sensor import (
    BaseSensor,
    MockSensor,
    SensorManager,
    SensorReading,
    SensorType,
    SerialSensor,
    get_sensor_manager,
)
from app.services.sampling import ingest_sync_samples, classify_status

logger = logging.getLogger(__name__)


@dataclass
class ChannelConfig:
    channel_id: int
    sensor_type_a: SensorType
    sensor_type_b: Optional[SensorType]
    port_a: Optional[str] = None
    port_b: Optional[str] = None
    baudrate_a: int = 9600
    baudrate_b: int = 9600
    calibration_offset_a: float = 0.0
    calibration_offset_b: float = 0.0
    use_mock: bool = True


class DataCollector:
    def __init__(
        self,
        session_local,
        sampling_interval_ms: int = 100,
        max_workers: int = 4,
    ):
        self.session_local = session_local
        self.sampling_interval_ms = sampling_interval_ms
        self.max_workers = max_workers
        self.sensor_manager = get_sensor_manager()
        self.config_manager = get_config_manager()
        self._running = False
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._collection_thread: Optional[threading.Thread] = None
        self._channels: Dict[int, ChannelConfig] = {}
        self._channel_data: Dict[int, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._callbacks: List[Callable[[Dict[int, Dict[str, Any]]], None]] = []

    def configure_channel(self, channel: Channel, use_mock: bool = True) -> None:
        config = ChannelConfig(
            channel_id=channel.id,
            sensor_type_a=channel.sensor_type_a,
            sensor_type_b=channel.sensor_type_b,
            calibration_offset_a=channel.calibration_offset_a,
            calibration_offset_b=channel.calibration_offset_b,
            use_mock=use_mock,
        )
        self._channels[channel.id] = config
        self._setup_sensors_for_channel(config, channel)

    def _setup_sensors_for_channel(self, config: ChannelConfig, channel: Channel) -> None:
        if config.use_mock:
            sensor_a = MockSensor(
                channel_id=config.channel_id,
                sensor_type=config.sensor_type_a,
                calibration_offset=config.calibration_offset_a,
                initial_value=100.0,
            )
            self.sensor_manager.register_sensor(config.channel_id, "sensor_a", sensor_a)

            if config.sensor_type_b:
                sensor_b = MockSensor(
                    channel_id=config.channel_id,
                    sensor_type=config.sensor_type_b,
                    calibration_offset=config.calibration_offset_b,
                    initial_value=95.0,
                )
                self.sensor_manager.register_sensor(config.channel_id, "sensor_b", sensor_b)
        else:
            if config.port_a:
                sensor_a = SerialSensor(
                    channel_id=config.channel_id,
                    sensor_type=config.sensor_type_a,
                    port=config.port_a,
                    baudrate=config.baudrate_a,
                    calibration_offset=config.calibration_offset_a,
                )
                self.sensor_manager.register_sensor(config.channel_id, "sensor_a", sensor_a)

            if config.sensor_type_b and config.port_b:
                sensor_b = SerialSensor(
                    channel_id=config.channel_id,
                    sensor_type=config.sensor_type_b,
                    port=config.port_b,
                    baudrate=config.baudrate_b,
                    calibration_offset=config.calibration_offset_b,
                )
                self.sensor_manager.register_sensor(config.channel_id, "sensor_b", sensor_b)

        logger.info(f"通道 {config.channel_id} 传感器配置完成")

    def remove_channel(self, channel_id: int) -> None:
        with self._lock:
            if channel_id in self._channels:
                del self._channels[channel_id]
            if channel_id in self._channel_data:
                del self._channel_data[channel_id]

        self.sensor_manager.unregister_sensor(channel_id, "sensor_a")
        self.sensor_manager.unregister_sensor(channel_id, "sensor_b")
        logger.info(f"通道 {channel_id} 已移除")

    def start(self) -> None:
        if self._running:
            logger.warning("采集服务已在运行")
            return

        self._running = True
        self._collection_thread = threading.Thread(target=self._collection_loop, daemon=True)
        self._collection_thread.start()
        logger.info(f"数据采集服务已启动，采样间隔: {self.sampling_interval_ms}ms")

    def stop(self) -> None:
        self._running = False
        if self._collection_thread:
            self._collection_thread.join(timeout=5.0)
        self._executor.shutdown(wait=True)
        self.sensor_manager.disconnect_all()
        logger.info("数据采集服务已停止")

    def _collection_loop(self) -> None:
        interval = self.sampling_interval_ms / 1000.0
        while self._running:
            try:
                start_time = time.time()
                self._collect_and_store()
                elapsed = time.time() - start_time
                sleep_time = max(0, interval - elapsed)
                time.sleep(sleep_time)
            except Exception as e:
                logger.error(f"采集循环异常: {e}")
                time.sleep(1.0)

    def _collect_and_store(self) -> None:
        if not self._channels:
            return

        readings = self.sensor_manager.read_all()
        sample_time = datetime.utcnow()

        points = []
        with self._lock:
            for channel_id, channel_readings in readings.items():
                if channel_id not in self._channels:
                    continue

                reading_a = channel_readings.get("sensor_a")
                reading_b = channel_readings.get("sensor_b")

                value_a = reading_a.value if reading_a and reading_a.value is not None else None
                value_b = reading_b.value if reading_b and reading_b.value is not None else None

                self._channel_data[channel_id] = {
                    "value_a": value_a,
                    "value_b": value_b,
                    "timestamp": sample_time,
                    "status_a": reading_a.status.value if reading_a else "disconnected",
                    "status_b": reading_b.status.value if reading_b else "disconnected",
                }

                if value_a is not None or value_b is not None:
                    points.append(
                        SamplePoint(
                            channel_id=channel_id,
                            value_a=value_a,
                            value_b=value_b,
                        )
                    )

        if points:
            payload = SyncSampleRequest(values=points, sample_time=sample_time)
            try:
                db = self.session_local()
                try:
                    ingest_sync_samples(db, payload)
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"存储采样数据失败: {e}")

        self._notify_callbacks()

    def _notify_callbacks(self) -> None:
        with self._lock:
            data_copy = self._channel_data.copy()

        for callback in self._callbacks:
            try:
                callback(data_copy)
            except Exception as e:
                logger.error(f"数据回调执行失败: {e}")

    def register_callback(self, callback: Callable[[Dict[int, Dict[str, Any]]], None]) -> None:
        self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[Dict[int, Dict[str, Any]]], None]) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def get_latest_data(self, channel_id: Optional[int] = None) -> Dict[int, Dict[str, Any]]:
        with self._lock:
            if channel_id is not None:
                return {channel_id: self._channel_data.get(channel_id, {})}
            return self._channel_data.copy()

    def update_sampling_interval(self, interval_ms: int) -> None:
        self.sampling_interval_ms = interval_ms
        logger.info(f"采样间隔已更新为: {interval_ms}ms")


_collector: Optional[DataCollector] = None


def init_collector(session_local, sampling_interval_ms: int = 100) -> DataCollector:
    global _collector
    if _collector is None:
        _collector = DataCollector(session_local, sampling_interval_ms)
    return _collector


def get_collector() -> Optional[DataCollector]:
    return _collector


def load_active_channels(db: Session, collector: DataCollector, use_mock: bool = True) -> None:
    channels = db.query(Channel).filter(Channel.status == ChannelStatus.active).all()
    for channel in channels:
        collector.configure_channel(channel, use_mock=use_mock)
    logger.info(f"已加载 {len(channels)} 个活动通道")
