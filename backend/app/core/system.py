import logging
import threading
import time
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.alarm.alarm import AlarmEvent, AlarmLevel, AlarmManager, AlarmRule, AlarmStatus
from app.config.config_manager import ConfigManager, ThresholdConfig, config_manager
from app.db.manager import DatabaseManager, db_manager
from app.fusion.fusion import DataFusion, FusionAlgorithm, FusionResult
from app.models.alarm import Alarm as AlarmModel
from app.models.channel import Channel
from app.models.liquid_level_data import DataStatus, LiquidLevelData
from app.sensor.sensor import SensorData, SensorManager, SensorParseError, SerialConnectionError

logger = logging.getLogger(__name__)


class SystemError(Exception):
    """系统异常"""
    pass


class MonitoringSystem:
    """监控系统主类 - 整合所有模块"""

    def __init__(self):
        self.sensor_manager = SensorManager()
        self.data_fusion = DataFusion(algorithm=FusionAlgorithm.AVERAGE)
        self.alarm_manager = AlarmManager()
        self.db_manager = db_manager
        self.config_manager = config_manager

        self._running = False
        self._main_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._data_buffer: dict[int, SensorData] = {}
        self._buffer_lock = threading.Lock()
        self._last_fusion_time: Optional[datetime] = None

        # 注册回调
        self.sensor_manager.add_callback(self._on_sensor_data)
        self.alarm_manager.add_callback(self._on_alarm_event)
        self.config_manager.add_callback(self._on_config_changed)

        # 从配置加载设置
        self._load_config()

    def _load_config(self) -> None:
        """从配置管理器加载设置"""
        system_config = self.config_manager.get_system()

        # 设置融合算法
        try:
            algorithm = FusionAlgorithm(system_config.fusion_algorithm)
            self.data_fusion = DataFusion(algorithm=algorithm)
            logger.info(f"融合算法设置为: {algorithm.value}")
        except ValueError:
            logger.warning(f"未知的融合算法: {system_config.fusion_algorithm}")

        # 加载传感器配置
        sensors_config = self.config_manager.get_config("sensors")
        for channel_id, sensor_conf in sensors_config.items():
            if sensor_conf.get("enabled", True):
                try:
                    self.sensor_manager.register_sensor(
                        channel_id=channel_id,
                        port=sensor_conf["port"],
                        baudrate=sensor_conf.get("baudrate", 9600),
                    )
                except Exception as e:
                    logger.error(f"注册传感器失败 通道 {channel_id}: {e}")

        # 加载报警规则
        thresholds_config = self.config_manager.get_config("thresholds")
        for channel_id, threshold_conf in thresholds_config.items():
            self._setup_alarm_rules(channel_id, ThresholdConfig.from_dict(threshold_conf))

    def _setup_alarm_rules(self, channel_id: int, config: ThresholdConfig) -> None:
        """设置报警规则"""
        # 低报警
        if config.warning_low > config.critical_low:
            self.alarm_manager.add_rule(AlarmRule(
                channel_id=channel_id,
                level=AlarmLevel.LOW,
                condition="<",
                threshold_value=config.warning_low,
                description=f"通道 {channel_id} 液位低于警告下限",
            ))

            self.alarm_manager.add_rule(AlarmRule(
                channel_id=channel_id,
                level=AlarmLevel.CRITICAL,
                condition="<",
                threshold_value=config.critical_low,
                description=f"通道 {channel_id} 液位低于危险下限",
            ))

        # 高报警
        if config.warning_high < config.critical_high:
            self.alarm_manager.add_rule(AlarmRule(
                channel_id=channel_id,
                level=AlarmLevel.HIGH,
                condition=">",
                threshold_value=config.warning_high,
                description=f"通道 {channel_id} 液位高于警告上限",
            ))

            self.alarm_manager.add_rule(AlarmRule(
                channel_id=channel_id,
                level=AlarmLevel.CRITICAL,
                condition=">",
                threshold_value=config.critical_high,
                description=f"通道 {channel_id} 液位高于危险上限",
            ))

    def _on_sensor_data(self, data: SensorData) -> None:
        """传感器数据回调"""
        try:
            # 应用校准偏移
            threshold_config = self.config_manager.get_threshold(data.channel_id)
            if threshold_config:
                data.value += threshold_config.calibration_offset

            # 存入缓冲区
            with self._buffer_lock:
                self._data_buffer[data.channel_id] = data

            # 检查报警
            self.alarm_manager.check_sensor_data(data)

            # 保存到数据库
            self._save_sensor_data(data)

        except Exception as e:
            logger.error(f"处理传感器数据时出错: {e}")

    def _on_alarm_event(self, event: AlarmEvent) -> None:
        """报警事件回调"""
        try:
            self._save_alarm_event(event)
        except Exception as e:
            logger.error(f"保存报警事件时出错: {e}")

    def _on_config_changed(self, config_type: str, config_data: dict) -> None:
        """配置变更回调"""
        logger.info(f"配置已变更: {config_type}")

        if config_type == "thresholds":
            # 重新加载报警规则
            self.alarm_manager.clear_rules()
            for channel_id, threshold_conf in config_data.items():
                self._setup_alarm_rules(channel_id, ThresholdConfig.from_dict(threshold_conf))

        elif config_type == "sensors":
            # 更新传感器配置
            for channel_id, sensor_conf in config_data.items():
                if sensor_conf.get("enabled", True):
                    # 检查是否需要重新注册
                    current_ports = self.sensor_manager.get_available_ports()
                    logger.debug(f"更新传感器配置: 通道 {channel_id}, 端口 {sensor_conf.get('port')}")

        elif config_type == "system":
            # 更新系统配置
            try:
                algorithm = FusionAlgorithm(config_data.get("fusion_algorithm", "average"))
                self.data_fusion = DataFusion(algorithm=algorithm)
                logger.info(f"融合算法已更新为: {algorithm.value}")
            except ValueError:
                logger.warning(f"未知的融合算法: {config_data.get('fusion_algorithm')}")

    def _save_sensor_data(self, data: SensorData) -> None:
        """保存传感器数据到数据库"""
        def save_operation(session: Session):
            # 获取通道信息
            channel = session.query(Channel).filter(Channel.id == data.channel_id).first()

            if channel is None:
                logger.warning(f"通道 {data.channel_id} 不存在，跳过数据保存")
                return

            # 确定数据状态
            status = self._classify_data_status(channel, data.value)

            # 创建数据记录
            record = LiquidLevelData(
                channel_id=data.channel_id,
                value=data.value,
                sample_time=data.timestamp,
                temperature=data.temperature,
                status=status,
            )
            session.add(record)

        try:
            with self.db_manager.get_session() as session:
                save_operation(session)
        except Exception as e:
            logger.error(f"保存传感器数据失败: {e}")

    def _classify_data_status(self, channel: Channel, value: float) -> DataStatus:
        """分类数据状态"""
        if value < channel.range_min or value > channel.range_max:
            return DataStatus.error
        if value < channel.warning_low or value > channel.warning_high:
            return DataStatus.warning
        return DataStatus.normal

    def _save_alarm_event(self, event: AlarmEvent) -> None:
        """保存报警事件到数据库"""
        def save_operation(session: Session):
            alarm = AlarmModel(
                channel_id=event.channel_id,
                level=event.level.value,
                threshold=event.threshold or 0.0,
                actual_value=event.value,
                occurred_at=event.occurred_at,
                description=event.message,
                resolved=event.status == AlarmStatus.RESOLVED,
                resolved_at=event.resolved_at,
            )
            session.add(alarm)

        try:
            with self.db_manager.get_session() as session:
                save_operation(session)
        except Exception as e:
            logger.error(f"保存报警事件失败: {e}")

    def _perform_fusion(self) -> Optional[FusionResult]:
        """执行数据融合"""
        with self._buffer_lock:
            if len(self._data_buffer) < 2:
                return None

            data_list = list(self._data_buffer.values())

        try:
            result = self.data_fusion.fuse(data_list)
            self._last_fusion_time = datetime.utcnow()
            logger.debug(f"数据融合完成: 值={result.fused_value:.2f}, 置信度={result.confidence:.2f}")

            # 检查融合结果报警
            self.alarm_manager.check_fusion_result(result)

            return result
        except Exception as e:
            logger.error(f"数据融合失败: {e}")
            return None

    def _main_loop(self) -> None:
        """主循环"""
        sample_interval = self.config_manager.get_system().sample_interval

        while not self._stop_event.is_set():
            try:
                loop_start = time.time()

                # 执行数据融合
                fusion_result = self._perform_fusion()
                if fusion_result:
                    logger.debug(f"融合结果: {fusion_result.to_dict()}")

                # 计算下一次采样时间
                elapsed = time.time() - loop_start
                sleep_time = max(0, sample_interval - elapsed)

                if sleep_time > 0:
                    self._stop_event.wait(sleep_time)

            except Exception as e:
                logger.error(f"主循环异常: {e}")
                time.sleep(1.0)

    def start(self) -> None:
        """启动系统"""
        if self._running:
            logger.warning("系统已在运行")
            return

        logger.info("正在启动监控系统...")

        # 测试数据库连接
        if not self.db_manager.test_connection():
            raise SystemError("数据库连接失败，无法启动系统")

        # 启动传感器采集
        try:
            self.sensor_manager.start()
        except Exception as e:
            logger.error(f"启动传感器采集失败: {e}")
            raise SystemError(f"启动传感器采集失败: {e}")

        # 启动主循环
        self._running = True
        self._stop_event.clear()
        self._main_thread = threading.Thread(
            target=self._main_loop,
            name="MonitoringMainLoop",
            daemon=True,
        )
        self._main_thread.start()

        logger.info("监控系统启动完成")

    def stop(self) -> None:
        """停止系统"""
        if not self._running:
            return

        logger.info("正在停止监控系统...")

        self._running = False
        self._stop_event.set()

        # 停止传感器采集
        self.sensor_manager.stop()

        # 停止配置热更新
        self.config_manager.stop_reload_thread()

        # 等待主循环结束
        if self._main_thread and self._main_thread.is_alive():
            self._main_thread.join(timeout=5.0)

        logger.info("监控系统已停止")

    def get_status(self) -> dict:
        """获取系统状态"""
        return {
            "running": self._running,
            "sensor_status": self.sensor_manager.get_sensor_status(),
            "active_alarms": len(self.alarm_manager.get_active_alarms()),
            "last_fusion_time": self._last_fusion_time.isoformat() if self._last_fusion_time else None,
            "buffered_data_count": len(self._data_buffer),
        }

    def acknowledge_alarm(self, alarm_id: str, user: str) -> bool:
        """确认报警"""
        result = self.alarm_manager.acknowledge_alarm(alarm_id, user)
        return result is not None

    def resolve_alarm(self, alarm_id: str) -> bool:
        """解决报警"""
        result = self.alarm_manager.resolve_alarm(alarm_id)
        return result is not None


# 全局系统实例
monitoring_system: Optional[MonitoringSystem] = None


def get_monitoring_system() -> MonitoringSystem:
    """获取监控系统实例（单例）"""
    global monitoring_system
    if monitoring_system is None:
        monitoring_system = MonitoringSystem()
    return monitoring_system
