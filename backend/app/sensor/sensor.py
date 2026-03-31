import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

import serial
import serial.tools.list_ports

logger = logging.getLogger(__name__)


class SensorError(Exception):
    """传感器基础异常"""
    pass


class SerialConnectionError(SensorError):
    """串口连接异常"""
    pass


class SensorParseError(SensorError):
    """传感器数据解析异常"""
    pass


class SensorType(str, Enum):
    """传感器类型"""
    CAPACITIVE = "capacitive"
    ULTRASONIC = "ultrasonic"
    LASER = "laser"


@dataclass
class SensorData:
    """传感器数据"""
    channel_id: int
    value: float
    timestamp: datetime
    temperature: Optional[float] = None
    raw_data: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "channel_id": self.channel_id,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "temperature": self.temperature,
            "raw_data": self.raw_data,
        }


class SerialSensorReader:
    """串口传感器读取器"""

    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        timeout: float = 1.0,
        reconnect_interval: float = 5.0,
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.reconnect_interval = reconnect_interval
        self._serial: Optional[serial.Serial] = None
        self._connected = False
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def connect(self) -> None:
        """连接串口"""
        try:
            with self._lock:
                if self._serial is not None and self._serial.is_open:
                    self._serial.close()

                self._serial = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=self.timeout,
                    write_timeout=self.timeout,
                )
                self._connected = True
                logger.info(f"串口 {self.port} 连接成功")
        except serial.SerialException as e:
            self._connected = False
            raise SerialConnectionError(f"串口 {self.port} 连接失败: {e}") from e

    def disconnect(self) -> None:
        """断开串口连接"""
        with self._lock:
            self._stop_event.set()
            if self._serial is not None and self._serial.is_open:
                try:
                    self._serial.close()
                    logger.info(f"串口 {self.port} 已断开")
                except Exception as e:
                    logger.warning(f"断开串口 {self.port} 时出错: {e}")
            self._connected = False

    def is_connected(self) -> bool:
        """检查连接状态"""
        with self._lock:
            return self._connected and self._serial is not None and self._serial.is_open

    def read_line(self) -> Optional[str]:
        """读取一行数据"""
        if not self.is_connected():
            return None

        try:
            with self._lock:
                if self._serial is None:
                    return None
                line = self._serial.readline()
                if line:
                    return line.decode("utf-8", errors="ignore").strip()
                return None
        except serial.SerialException as e:
            logger.error(f"串口 {self.port} 读取失败: {e}")
            self._connected = False
            raise SerialConnectionError(f"串口读取失败: {e}") from e

    def write(self, data: bytes) -> None:
        """写入数据"""
        if not self.is_connected():
            raise SerialConnectionError(f"串口 {self.port} 未连接")

        try:
            with self._lock:
                if self._serial is not None:
                    self._serial.write(data)
        except serial.SerialException as e:
            logger.error(f"串口 {self.port} 写入失败: {e}")
            self._connected = False
            raise SerialConnectionError(f"串口写入失败: {e}") from e


class SensorManager:
    """传感器管理器 - 负责多通道传感器数据采集"""

    def __init__(self):
        self._readers: dict[int, SerialSensorReader] = {}
        self._callbacks: list[Callable[[SensorData], None]] = []
        self._running = False
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()

    def register_sensor(
        self,
        channel_id: int,
        port: str,
        baudrate: int = 9600,
    ) -> None:
        """注册传感器"""
        with self._lock:
            if channel_id in self._readers:
                logger.warning(f"通道 {channel_id} 已存在，将重新注册")
                self._readers[channel_id].disconnect()

            reader = SerialSensorReader(port=port, baudrate=baudrate)
            self._readers[channel_id] = reader
            logger.info(f"传感器已注册: 通道 {channel_id} -> 端口 {port}")

    def unregister_sensor(self, channel_id: int) -> None:
        """注销传感器"""
        with self._lock:
            if channel_id in self._readers:
                self._readers[channel_id].disconnect()
                del self._readers[channel_id]
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

    def _parse_sensor_data(self, channel_id: int, raw_line: str) -> Optional[SensorData]:
        """解析传感器数据"""
        try:
            # 支持 JSON 格式: {"value": 123.45, "temp": 25.0}
            if raw_line.startswith("{") and raw_line.endswith("}"):
                parsed = json.loads(raw_line)
                return SensorData(
                    channel_id=channel_id,
                    value=float(parsed.get("value", 0)),
                    timestamp=datetime.utcnow(),
                    temperature=parsed.get("temp") or parsed.get("temperature"),
                    raw_data=raw_line,
                )

            # 支持 CSV 格式: value,temp
            if "," in raw_line:
                parts = raw_line.split(",")
                value = float(parts[0].strip())
                temp = float(parts[1].strip()) if len(parts) > 1 else None
                return SensorData(
                    channel_id=channel_id,
                    value=value,
                    timestamp=datetime.utcnow(),
                    temperature=temp,
                    raw_data=raw_line,
                )

            # 支持简单数值格式
            value = float(raw_line.strip())
            return SensorData(
                channel_id=channel_id,
                value=value,
                timestamp=datetime.utcnow(),
                raw_data=raw_line,
            )

        except json.JSONDecodeError as e:
            raise SensorParseError(f"JSON解析失败: {raw_line}") from e
        except ValueError as e:
            raise SensorParseError(f"数值解析失败: {raw_line}") from e

    def _read_loop(self, channel_id: int, reader: SerialSensorReader) -> None:
        """传感器读取循环"""
        while self._running and not reader._stop_event.is_set():
            try:
                if not reader.is_connected():
                    try:
                        reader.connect()
                    except SerialConnectionError as e:
                        logger.warning(f"串口重连失败: {e}, {reader.reconnect_interval}秒后重试")
                        time.sleep(reader.reconnect_interval)
                        continue

                raw_line = reader.read_line()
                if raw_line:
                    try:
                        data = self._parse_sensor_data(channel_id, raw_line)
                        if data:
                            self._notify_callbacks(data)
                    except SensorParseError as e:
                        logger.warning(f"数据解析错误: {e}")

            except SerialConnectionError as e:
                logger.error(f"串口连接错误: {e}")
                time.sleep(reader.reconnect_interval)
            except Exception as e:
                logger.error(f"读取循环异常: {e}")
                time.sleep(1.0)

    def start(self) -> None:
        """启动所有传感器采集"""
        if self._running:
            logger.warning("传感器管理器已在运行")
            return

        self._running = True
        self._threads = []

        with self._lock:
            for channel_id, reader in self._readers.items():
                thread = threading.Thread(
                    target=self._read_loop,
                    args=(channel_id, reader),
                    name=f"SensorThread-{channel_id}",
                    daemon=True,
                )
                thread.start()
                self._threads.append(thread)
                logger.info(f"传感器采集线程已启动: 通道 {channel_id}")

    def stop(self) -> None:
        """停止所有传感器采集"""
        self._running = False

        with self._lock:
            for reader in self._readers.values():
                reader.disconnect()

        for thread in self._threads:
            thread.join(timeout=2.0)

        logger.info("传感器管理器已停止")

    def get_available_ports(self) -> list[str]:
        """获取可用串口列表"""
        return [port.device for port in serial.tools.list_ports.comports()]

    def get_sensor_status(self) -> dict[int, bool]:
        """获取传感器连接状态"""
        with self._lock:
            return {
                channel_id: reader.is_connected()
                for channel_id, reader in self._readers.items()
            }
