"""
多通道液位传感器数据采集引擎
支持多进程/异步采集、数据融合、持久化和告警
"""

import asyncio
import json
import logging
import multiprocessing as mp
import signal
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Callable, Optional

from app.alarm.alarm import AlarmEvent, AlarmLevel, AlarmManager, AlarmRule, AlarmStatus
from app.config.config_manager import ConfigManager, SensorConfig, SystemConfig, ThresholdConfig
from app.db.manager import DatabaseManager, db_manager
from app.fusion.fusion import DataFusion, FusionAlgorithm, FusionResult
from app.sensor.sensor import SensorData, SensorManager, SensorParseError, SerialConnectionError

logger = logging.getLogger(__name__)


class EngineStatus(str, Enum):
    """引擎状态"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    SHUTTING_DOWN = "shutting_down"


@dataclass
class ChannelState:
    """通道状态"""
    channel_id: int
    enabled: bool = True
    connected: bool = False
    last_value: Optional[float] = None
    last_timestamp: Optional[datetime] = None
    error_count: int = 0
    sample_count: int = 0


@dataclass
class EngineStats:
    """引擎统计信息"""
    total_samples: int = 0
    total_fusions: int = 0
    total_alarms: int = 0
    errors_count: int = 0
    start_time: Optional[datetime] = None
    last_sample_time: Optional[datetime] = None


class DataCollector:
    """
    数据采集器 - 负责多通道传感器数据的并行采集
    支持多线程和多进程模式
    """

    def __init__(
        self,
        config_manager: ConfigManager,
        use_multiprocessing: bool = False,
        max_workers: int = 4,
    ):
        self.config_manager = config_manager
        self.use_multiprocessing = use_multiprocessing
        self.max_workers = max_workers

        self._sensor_manager = SensorManager()
        self._data_queue: Queue = Queue(maxsize=1000)
        self._running = False
        self._executor: Optional[ThreadPoolExecutor | ProcessPoolExecutor] = None
        self._futures: list = []
        self._channel_states: dict[int, ChannelState] = {}
        self._lock = threading.RLock()
        self._callbacks: list[Callable[[SensorData], None]] = []

    def _load_sensor_configs(self) -> dict[int, SensorConfig]:
        """加载传感器配置"""
        configs = {}
        data = self.config_manager.get_config("sensors")
        if data:
            for channel_id, config_data in data.items():
                try:
                    configs[int(channel_id)] = SensorConfig.from_dict(config_data)
                except Exception as e:
                    logger.error(f"解析传感器配置失败: {config_data}, 错误: {e}")
        return configs

    def _collect_channel_data(self, channel_id: int, config: SensorConfig) -> Optional[SensorData]:
        """采集单个通道数据（用于多进程）"""
        if not config.enabled:
            return None

        try:
            # 这里使用模拟数据，实际应用中应连接真实传感器
            import random
            value = random.uniform(20.0, 80.0)

            return SensorData(
                channel_id=channel_id,
                value=value,
                timestamp=datetime.utcnow(),
                temperature=random.uniform(20.0, 30.0),
                raw_data=json.dumps({"value": value}),
            )
        except Exception as e:
            logger.error(f"通道 {channel_id} 数据采集失败: {e}")
            return None

    def _sensor_callback(self, data: SensorData) -> None:
        """传感器数据回调"""
        try:
            self._data_queue.put(data, block=False)

            with self._lock:
                if data.channel_id in self._channel_states:
                    state = self._channel_states[data.channel_id]
                    state.last_value = data.value
                    state.last_timestamp = data.timestamp
                    state.sample_count += 1
                    state.connected = True

            # 通知外部回调
            for callback in self._callbacks:
                try:
                    callback(data)
                except Exception as e:
                    logger.error(f"数据回调执行失败: {e}")

        except Exception as e:
            logger.error(f"处理传感器数据失败: {e}")

    def add_callback(self, callback: Callable[[SensorData], None]) -> None:
        """添加数据回调"""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[SensorData], None]) -> None:
        """移除数据回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def start(self) -> None:
        """启动数据采集"""
        if self._running:
            logger.warning("数据采集器已在运行")
            return

        self._running = True
        configs = self._load_sensor_configs()

        if not configs:
            logger.warning("没有可用的传感器配置")
            return

        # 初始化通道状态
        with self._lock:
            self._channel_states = {
                channel_id: ChannelState(channel_id=channel_id, enabled=config.enabled)
                for channel_id, config in configs.items()
            }

        if self.use_multiprocessing:
            self._start_multiprocess_mode(configs)
        else:
            self._start_multithread_mode(configs)

        logger.info(f"数据采集器已启动，模式: {'多进程' if self.use_multiprocessing else '多线程'}")

    def _start_multithread_mode(self, configs: dict[int, SensorConfig]) -> None:
        """启动多线程模式"""
        self._sensor_manager.add_callback(self._sensor_callback)

        for channel_id, config in configs.items():
            if config.enabled:
                self._sensor_manager.register_sensor(
                    channel_id=channel_id,
                    port=config.port,
                    baudrate=config.baudrate,
                )

        self._sensor_manager.start()

    def _start_multiprocess_mode(self, configs: dict[int, SensorConfig]) -> None:
        """启动多进程模式"""
        self._executor = ProcessPoolExecutor(max_workers=self.max_workers)

        def collect_loop():
            """采集循环"""
            while self._running:
                futures = []
                for channel_id, config in configs.items():
                    if config.enabled:
                        future = self._executor.submit(
                            self._collect_channel_data, channel_id, config
                        )
                        futures.append((channel_id, future))

                for channel_id, future in futures:
                    try:
                        data = future.result(timeout=5.0)
                        if data:
                            self._sensor_callback(data)
                    except Exception as e:
                        logger.error(f"通道 {channel_id} 采集失败: {e}")
                        with self._lock:
                            if channel_id in self._channel_states:
                                self._channel_states[channel_id].error_count += 1

                time.sleep(0.1)  # 短暂休眠避免CPU占用过高

        self._collect_thread = threading.Thread(target=collect_loop, daemon=True)
        self._collect_thread.start()

    def stop(self) -> None:
        """停止数据采集"""
        self._running = False

        if not self.use_multiprocessing:
            self._sensor_manager.stop()
        else:
            if self._executor:
                self._executor.shutdown(wait=True)

        logger.info("数据采集器已停止")

    def get_data(self, timeout: float = 0.1) -> Optional[SensorData]:
        """从队列获取数据"""
        try:
            return self._data_queue.get(timeout=timeout)
        except Empty:
            return None

    def get_channel_states(self) -> dict[int, ChannelState]:
        """获取通道状态"""
        with self._lock:
            return dict(self._channel_states)


class AcquisitionEngine:
    """
    采集引擎 - 系统核心组件
    整合数据采集、融合、持久化和告警功能
    """

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        alarm_manager: Optional[AlarmManager] = None,
        use_multiprocessing: bool = False,
    ):
        self.config_manager = config_manager or ConfigManager()
        self.alarm_manager = alarm_manager or AlarmManager()
        self.use_multiprocessing = use_multiprocessing

        self._data_collector = DataCollector(
            config_manager=self.config_manager,
            use_multiprocessing=use_multiprocessing,
        )
        self._data_fusion = DataFusion(algorithm=FusionAlgorithm.AVERAGE)
        self._db_manager = db_manager

        self._status = EngineStatus.STOPPED
        self._stats = EngineStats()
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        # 数据缓冲区（用于时间戳对齐）
        self._data_buffer: dict[int, SensorData] = {}
        self._buffer_timeout = 0.5  # 缓冲区超时时间（秒）
        self._last_fusion_time: Optional[datetime] = None

        # 配置变更回调
        self.config_manager.add_callback(self._on_config_changed)

        # 注册告警回调
        self._data_collector.add_callback(self._on_sensor_data)

    def _on_config_changed(self, config_type: str, config_data: Any) -> None:
        """配置变更回调"""
        logger.info(f"配置已更新: {config_type}")

        if config_type == "system":
            try:
                system_config = SystemConfig.from_dict(config_data)
                self._data_fusion.algorithm = FusionAlgorithm(system_config.fusion_algorithm)
                logger.info(f"融合算法已更新: {system_config.fusion_algorithm}")
            except Exception as e:
                logger.error(f"更新系统配置失败: {e}")

    def _on_sensor_data(self, data: SensorData) -> None:
        """传感器数据回调"""
        # 检查告警规则
        alarms = self.alarm_manager.check_sensor_data(data)
        if alarms:
            with self._lock:
                self._stats.total_alarms += len(alarms)

        # 存入缓冲区等待融合
        self._data_buffer[data.channel_id] = data

    def _fuse_and_persist(self) -> None:
        """执行数据融合和持久化"""
        if not self._data_buffer:
            return

        # 获取系统配置
        system_config = self.config_manager.get_system()

        # 检查是否达到采集间隔
        now = datetime.utcnow()
        if self._last_fusion_time:
            elapsed = (now - self._last_fusion_time).total_seconds()
            if elapsed < system_config.sample_interval:
                return

        # 获取所有启用的通道
        sensor_configs = self.config_manager.get_config("sensors")
        enabled_channels = {
            int(cid) for cid, cfg in sensor_configs.items()
            if cfg.get("enabled", False)
        }

        # 检查是否收集到所有通道的数据
        available_channels = set(self._data_buffer.keys())

        if not available_channels:
            return

        # 执行数据融合
        data_list = list(self._data_buffer.values())

        try:
            fusion_result = self._data_fusion.fuse(data_list)
            self._last_fusion_time = now

            with self._lock:
                self._stats.total_fusions += 1

            # 检查融合结果告警
            alarms = self.alarm_manager.check_fusion_result(fusion_result)
            if alarms:
                with self._lock:
                    self._stats.total_alarms += len(alarms)

            # 持久化到数据库
            self._persist_data(data_list, fusion_result)

            # 清空缓冲区
            self._data_buffer.clear()

            logger.debug(f"数据融合完成: value={fusion_result.fused_value:.2f}, "
                        f"confidence={fusion_result.confidence:.2f}")

        except Exception as e:
            logger.error(f"数据融合失败: {e}")
            with self._lock:
                self._stats.errors_count += 1

    def _persist_data(
        self,
        data_list: list[SensorData],
        fusion_result: FusionResult,
    ) -> None:
        """持久化数据到数据库"""
        try:
            def save_operation(session):
                from app.models.liquid_level_data import LiquidLevelData, DataStatus
                from app.models.channel import Channel

                for data in data_list:
                    # 获取通道配置
                    threshold_config = self.config_manager.get_threshold(data.channel_id)

                    # 确定数据状态
                    status = DataStatus.normal
                    if threshold_config:
                        if (data.value < threshold_config.warning_low or
                            data.value > threshold_config.warning_high):
                            status = DataStatus.warning
                        if (data.value < threshold_config.critical_low or
                            data.value > threshold_config.critical_high):
                            status = DataStatus.error

                    record = LiquidLevelData(
                        channel_id=data.channel_id,
                        value=data.value,
                        sample_time=data.timestamp,
                        temperature=data.temperature,
                        status=status,
                    )
                    session.add(record)

                session.commit()

            self._db_manager.execute_with_retry(save_operation)

            with self._lock:
                self._stats.total_samples += len(data_list)
                self._stats.last_sample_time = datetime.utcnow()

        except Exception as e:
            logger.error(f"数据持久化失败: {e}")
            with self._lock:
                self._stats.errors_count += 1

    def _worker_loop(self) -> None:
        """工作线程主循环"""
        logger.info("采集引擎工作线程已启动")

        while not self._stop_event.is_set():
            try:
                # 从数据采集器获取数据
                data = self._data_collector.get_data(timeout=0.1)

                if data:
                    with self._lock:
                        self._stats.total_samples += 1

                # 执行融合和持久化
                self._fuse_and_persist()

            except Exception as e:
                logger.error(f"工作线程异常: {e}")
                with self._lock:
                    self._stats.errors_count += 1

            time.sleep(0.01)  # 短暂休眠

        logger.info("采集引擎工作线程已停止")

    def start(self) -> None:
        """启动采集引擎"""
        if self._status == EngineStatus.RUNNING:
            logger.warning("采集引擎已在运行")
            return

        with self._lock:
            self._status = EngineStatus.STARTING

        try:
            # 启动数据采集器
            self._data_collector.start()

            # 启动工作线程
            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                name="AcquisitionEngineWorker",
                daemon=True,
            )
            self._worker_thread.start()

            with self._lock:
                self._status = EngineStatus.RUNNING
                self._stats.start_time = datetime.utcnow()

            logger.info("采集引擎已启动")

        except Exception as e:
            logger.error(f"启动采集引擎失败: {e}")
            with self._lock:
                self._status = EngineStatus.ERROR
            raise

    def stop(self) -> None:
        """停止采集引擎"""
        if self._status != EngineStatus.RUNNING:
            logger.warning("采集引擎未在运行")
            return

        with self._lock:
            self._status = EngineStatus.SHUTTING_DOWN

        logger.info("正在停止采集引擎...")

        # 停止工作线程
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5.0)

        # 停止数据采集器
        self._data_collector.stop()

        with self._lock:
            self._status = EngineStatus.STOPPED

        logger.info("采集引擎已停止")

    def pause(self) -> None:
        """暂停采集"""
        if self._status == EngineStatus.RUNNING:
            with self._lock:
                self._status = EngineStatus.PAUSED
            logger.info("采集引擎已暂停")

    def resume(self) -> None:
        """恢复采集"""
        if self._status == EngineStatus.PAUSED:
            with self._lock:
                self._status = EngineStatus.RUNNING
            logger.info("采集引擎已恢复")

    def get_status(self) -> EngineStatus:
        """获取引擎状态"""
        with self._lock:
            return self._status

    def get_stats(self) -> EngineStats:
        """获取统计信息"""
        with self._lock:
            return EngineStats(
                total_samples=self._stats.total_samples,
                total_fusions=self._stats.total_fusions,
                total_alarms=self._stats.total_alarms,
                errors_count=self._stats.errors_count,
                start_time=self._stats.start_time,
                last_sample_time=self._stats.last_sample_time,
            )

    def get_channel_states(self) -> dict[int, ChannelState]:
        """获取通道状态"""
        return self._data_collector.get_channel_states()

    def get_latest_data(self) -> dict[int, SensorData]:
        """获取最新数据"""
        return dict(self._data_buffer)


# 全局引擎实例
_engine: Optional[AcquisitionEngine] = None


def get_engine() -> AcquisitionEngine:
    """获取全局引擎实例"""
    global _engine
    if _engine is None:
        _engine = AcquisitionEngine()
    return _engine


def start_engine() -> None:
    """启动全局引擎"""
    engine = get_engine()
    engine.start()


def stop_engine() -> None:
    """停止全局引擎"""
    global _engine
    if _engine is not None:
        _engine.stop()
        _engine = None


def signal_handler(signum, frame):
    """信号处理函数"""
    logger.info(f"接收到信号 {signum}，正在关闭引擎...")
    stop_engine()
    sys.exit(0)


# 注册信号处理
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
