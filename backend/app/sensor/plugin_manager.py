"""
传感器插件管理器
整合插件系统与传感器管理
"""

import logging
import threading
import time
from typing import Callable, Optional

from app.sensor.sensor import SensorData, SensorManager
from app.sensor.plugins import SensorPluginRegistry, BaseSensorDriver
from app.config.config_manager import ConfigManager

logger = logging.getLogger(__name__)

# 自动导入所有插件
from app.sensor.plugins import mock_sensor
from app.sensor.plugins import ultrasonic_sensor
from app.sensor.plugins import infrared_sensor
from app.sensor.plugins import capacitive_sensor


class PluginBasedSensorManager:
    """
    基于插件的传感器管理器
    支持动态加载不同类型的传感器驱动
    """

    def __init__(self, config_manager: Optional[ConfigManager] = None):
        self.config_manager = config_manager or ConfigManager()
        self._drivers: dict[int, BaseSensorDriver] = {}
        self._callbacks: list[Callable[[SensorData], None]] = []
        self._running = False
        self._threads: list[threading.Thread] = []
        self._lock = threading.RLock()
        self._stop_event = threading.Event()

        logger.info(f"已加载的传感器驱动类型: {SensorPluginRegistry.list_drivers()}")

    def register_sensor(
        self,
        channel_id: int,
        sensor_type: str,
        config: dict,
    ) -> bool:
        """注册传感器"""
        try:
            with self._lock:
                # 如果已存在，先断开
                if channel_id in self._drivers:
                    self._drivers[channel_id].disconnect()
                    del self._drivers[channel_id]

                # 创建驱动实例
                driver = SensorPluginRegistry.create_driver(
                    sensor_type=sensor_type,
                    channel_id=channel_id,
                    config=config,
                )

                if driver is None:
                    logger.error(f"无法创建传感器驱动: {sensor_type}")
                    return False

                self._drivers[channel_id] = driver
                logger.info(f"传感器已注册: 通道 {channel_id}, 类型 {sensor_type}")
                return True

        except Exception as e:
            logger.error(f"注册传感器失败: {e}")
            return False

    def unregister_sensor(self, channel_id: int) -> None:
        """注销传感器"""
        with self._lock:
            if channel_id in self._drivers:
                self._drivers[channel_id].disconnect()
                del self._drivers[channel_id]
                logger.info(f"传感器已注销: 通道 {channel_id}")

    def add_callback(self, callback: Callable[[SensorData], None]) -> None:
        """添加数据回调"""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[SensorData], None]) -> None:
        """移除数据回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _notify_callbacks(self, data: SensorData) -> None:
        """通知所有回调"""
        for callback in self._callbacks:
            try:
                callback(data)
            except Exception as e:
                logger.error(f"数据回调执行失败: {e}")

    def _read_loop(self, channel_id: int, driver: BaseSensorDriver, interval: float = 1.0) -> None:
        """传感器读取循环"""
        reconnect_interval = 5.0

        while self._running and not self._stop_event.is_set():
            try:
                # 检查连接状态
                if not driver.is_connected():
                    try:
                        driver.connect()
                        logger.info(f"传感器 {channel_id} 已连接")
                    except Exception as e:
                        logger.warning(f"传感器 {channel_id} 连接失败: {e}, {reconnect_interval}秒后重试")
                        time.sleep(reconnect_interval)
                        continue

                # 读取数据
                data = driver.read()
                if data:
                    self._notify_callbacks(data)

                # 等待下一次采集
                time.sleep(interval)

            except Exception as e:
                logger.error(f"传感器 {channel_id} 读取循环异常: {e}")
                time.sleep(reconnect_interval)

    def start(self, interval: float = 1.0) -> None:
        """启动所有传感器采集"""
        if self._running:
            logger.warning("传感器管理器已在运行")
            return

        self._running = True
        self._stop_event.clear()
        self._threads = []

        with self._lock:
            for channel_id, driver in self._drivers.items():
                thread = threading.Thread(
                    target=self._read_loop,
                    args=(channel_id, driver, interval),
                    name=f"SensorThread-{channel_id}",
                    daemon=True,
                )
                thread.start()
                self._threads.append(thread)
                logger.info(f"传感器采集线程已启动: 通道 {channel_id}")

    def stop(self) -> None:
        """停止所有传感器采集"""
        self._running = False
        self._stop_event.set()

        with self._lock:
            for driver in self._drivers.values():
                try:
                    driver.disconnect()
                except Exception as e:
                    logger.warning(f"断开传感器时出错: {e}")

        for thread in self._threads:
            thread.join(timeout=2.0)

        logger.info("传感器管理器已停止")

    def get_driver(self, channel_id: int) -> Optional[BaseSensorDriver]:
        """获取传感器驱动"""
        with self._lock:
            return self._drivers.get(channel_id)

    def get_all_drivers(self) -> dict[int, BaseSensorDriver]:
        """获取所有传感器驱动"""
        with self._lock:
            return dict(self._drivers)

    def get_channel_status(self, channel_id: int) -> dict:
        """获取通道状态"""
        with self._lock:
            driver = self._drivers.get(channel_id)
            if driver:
                return {
                    "channel_id": channel_id,
                    "sensor_type": driver.sensor_type,
                    "connected": driver.is_connected(),
                    "capabilities": {
                        "supports_temperature": driver.capabilities.supports_temperature,
                        "min_range": driver.capabilities.min_range,
                        "max_range": driver.capabilities.max_range,
                        "accuracy": driver.capabilities.accuracy,
                    },
                }
            return {"channel_id": channel_id, "error": "通道不存在"}

    def load_from_config(self) -> None:
        """从配置加载传感器"""
        sensors_config = self.config_manager.get_config("sensors")

        if not sensors_config:
            logger.warning("配置中没有传感器信息")
            return

        for channel_id_str, config in sensors_config.items():
            try:
                channel_id = int(channel_id_str)
                sensor_type = config.get("sensor_type", "mock")
                enabled = config.get("enabled", True)

                if enabled:
                    # 合并配置
                    full_config = {
                        "port": config.get("port", f"COM{channel_id}"),
                        "baudrate": config.get("baudrate", 9600),
                        **config,  # 包含所有其他配置项
                    }
                    self.register_sensor(channel_id, sensor_type, full_config)
                else:
                    logger.info(f"传感器 {channel_id} 已禁用，跳过")

            except Exception as e:
                logger.error(f"加载传感器配置失败: {config}, 错误: {e}")

        logger.info(f"从配置加载了 {len(self._drivers)} 个传感器")


# 全局管理器实例
_plugin_manager: Optional[PluginBasedSensorManager] = None


def get_plugin_manager() -> PluginBasedSensorManager:
    """获取全局插件管理器实例"""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginBasedSensorManager()
    return _plugin_manager
