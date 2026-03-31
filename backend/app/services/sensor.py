import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SensorType(str, Enum):
    capacitive = "capacitive"
    ultrasonic = "ultrasonic"
    laser = "laser"


class SensorStatus(str, Enum):
    normal = "normal"
    disconnected = "disconnected"
    error = "error"
    timeout = "timeout"


@dataclass
class SensorReading:
    sensor_type: SensorType
    channel_id: int
    value: Optional[float]
    raw_value: Optional[float]
    timestamp: datetime
    status: SensorStatus
    error_message: Optional[str] = None


class SensorError(Exception):
    pass


class SensorDisconnectedError(SensorError):
    pass


class SensorTimeoutError(SensorError):
    pass


class SensorReadError(SensorError):
    pass


class BaseSensor(ABC):
    def __init__(
        self,
        channel_id: int,
        sensor_type: SensorType,
        calibration_offset: float = 0.0,
    ):
        self.channel_id = channel_id
        self.sensor_type = sensor_type
        self.calibration_offset = calibration_offset
        self._connected = False
        self._last_reading: Optional[SensorReading] = None
        self._error_count = 0
        self._lock = threading.Lock()

    @abstractmethod
    def connect(self) -> bool:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @abstractmethod
    def read_raw(self) -> Tuple[Optional[float], Optional[str]]:
        pass

    def read(self) -> SensorReading:
        timestamp = datetime.utcnow()

        with self._lock:
            if not self._connected:
                try:
                    if not self.connect():
                        return SensorReading(
                            sensor_type=self.sensor_type,
                            channel_id=self.channel_id,
                            value=None,
                            raw_value=None,
                            timestamp=timestamp,
                            status=SensorStatus.disconnected,
                            error_message="传感器未连接",
                        )
                except Exception as e:
                    logger.error(f"通道 {self.channel_id} 传感器连接失败: {e}")
                    return SensorReading(
                        sensor_type=self.sensor_type,
                        channel_id=self.channel_id,
                        value=None,
                        raw_value=None,
                        timestamp=timestamp,
                        status=SensorStatus.disconnected,
                        error_message=str(e),
                    )

            try:
                raw_value, error = self.read_raw()

                if error:
                    self._error_count += 1
                    logger.warning(f"通道 {self.channel_id} 传感器读取错误: {error}")
                    return SensorReading(
                        sensor_type=self.sensor_type,
                        channel_id=self.channel_id,
                        value=None,
                        raw_value=raw_value,
                        timestamp=timestamp,
                        status=SensorStatus.error,
                        error_message=error,
                    )

                if raw_value is None:
                    self._error_count += 1
                    return SensorReading(
                        sensor_type=self.sensor_type,
                        channel_id=self.channel_id,
                        value=None,
                        raw_value=None,
                        timestamp=timestamp,
                        status=SensorStatus.error,
                        error_message="读取值为空",
                    )

                calibrated_value = raw_value + self.calibration_offset
                self._error_count = 0
                self._last_reading = SensorReading(
                    sensor_type=self.sensor_type,
                    channel_id=self.channel_id,
                    value=calibrated_value,
                    raw_value=raw_value,
                    timestamp=timestamp,
                    status=SensorStatus.normal,
                )
                return self._last_reading

            except SensorDisconnectedError as e:
                self._connected = False
                logger.error(f"通道 {self.channel_id} 传感器断开: {e}")
                return SensorReading(
                    sensor_type=self.sensor_type,
                    channel_id=self.channel_id,
                    value=None,
                    raw_value=None,
                    timestamp=timestamp,
                    status=SensorStatus.disconnected,
                    error_message=str(e),
                )
            except SensorTimeoutError as e:
                logger.warning(f"通道 {self.channel_id} 传感器超时: {e}")
                return SensorReading(
                    sensor_type=self.sensor_type,
                    channel_id=self.channel_id,
                    value=None,
                    raw_value=None,
                    timestamp=timestamp,
                    status=SensorStatus.timeout,
                    error_message=str(e),
                )
            except Exception as e:
                logger.error(f"通道 {self.channel_id} 传感器读取异常: {e}")
                return SensorReading(
                    sensor_type=self.sensor_type,
                    channel_id=self.channel_id,
                    value=None,
                    raw_value=None,
                    timestamp=timestamp,
                    status=SensorStatus.error,
                    error_message=str(e),
                )

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def last_reading(self) -> Optional[SensorReading]:
        return self._last_reading

    def set_calibration_offset(self, offset: float) -> None:
        with self._lock:
            self.calibration_offset = offset


class SerialSensor(BaseSensor):
    def __init__(
        self,
        channel_id: int,
        sensor_type: SensorType,
        port: str,
        baudrate: int = 9600,
        calibration_offset: float = 0.0,
        timeout: float = 1.0,
    ):
        super().__init__(channel_id, sensor_type, calibration_offset)
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial_conn = None

    def connect(self) -> bool:
        try:
            import serial

            if self._serial_conn is not None and self._serial_conn.is_open:
                self._connected = True
                return True

            self._serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
            )
            self._connected = True
            logger.info(f"通道 {self.channel_id} 串口连接成功: {self.port}")
            return True

        except ImportError:
            logger.error("pyserial库未安装")
            return False
        except Exception as e:
            logger.error(f"通道 {self.channel_id} 串口连接失败: {e}")
            self._connected = False
            return False

    def disconnect(self) -> None:
        if self._serial_conn is not None:
            try:
                self._serial_conn.close()
            except Exception as e:
                logger.warning(f"通道 {self.channel_id} 关闭串口失败: {e}")
            finally:
                self._serial_conn = None
                self._connected = False

    def read_raw(self) -> Tuple[Optional[float], Optional[str]]:
        if self._serial_conn is None or not self._serial_conn.is_open:
            raise SensorDisconnectedError("串口未连接")

        try:
            self._serial_conn.write(b"READ\n")
            time.sleep(0.01)

            if self._serial_conn.in_waiting > 0:
                response = self._serial_conn.readline().decode("utf-8").strip()
                try:
                    return float(response), None
                except ValueError:
                    return None, f"无效数据格式: {response}"
            else:
                return None, "无响应数据"

        except Exception as e:
            if "could not open port" in str(e).lower():
                raise SensorDisconnectedError(f"串口断开: {e}")
            raise SensorReadError(f"读取失败: {e}")


class MockSensor(BaseSensor):
    def __init__(
        self,
        channel_id: int,
        sensor_type: SensorType,
        calibration_offset: float = 0.0,
        initial_value: float = 100.0,
    ):
        super().__init__(channel_id, sensor_type, calibration_offset)
        self._initial_value = initial_value
        self._current_value = initial_value

    def connect(self) -> bool:
        self._connected = True
        logger.debug(f"通道 {self.channel_id} 模拟传感器已连接")
        return True

    def disconnect(self) -> None:
        self._connected = False

    def read_raw(self) -> Tuple[Optional[float], Optional[str]]:
        import random

        noise = random.uniform(-0.5, 0.5)
        self._current_value = self._initial_value + noise
        return self._current_value, None

    def set_value(self, value: float) -> None:
        self._initial_value = value


class SensorManager:
    def __init__(self):
        self._sensors: Dict[int, Dict[str, BaseSensor]] = {}
        self._lock = threading.Lock()

    def register_sensor(
        self,
        channel_id: int,
        sensor_key: str,
        sensor: BaseSensor,
    ) -> None:
        with self._lock:
            if channel_id not in self._sensors:
                self._sensors[channel_id] = {}
            self._sensors[channel_id][sensor_key] = sensor
            logger.info(f"注册传感器: 通道 {channel_id}, 键 {sensor_key}")

    def unregister_sensor(self, channel_id: int, sensor_key: str) -> None:
        with self._lock:
            if channel_id in self._sensors and sensor_key in self._sensors[channel_id]:
                sensor = self._sensors[channel_id].pop(sensor_key)
                sensor.disconnect()
                logger.info(f"注销传感器: 通道 {channel_id}, 键 {sensor_key}")

    def get_sensor(self, channel_id: int, sensor_key: str) -> Optional[BaseSensor]:
        with self._lock:
            return self._sensors.get(channel_id, {}).get(sensor_key)

    def read_channel(self, channel_id: int) -> Dict[str, SensorReading]:
        readings: Dict[str, SensorReading] = {}
        with self._lock:
            sensors = self._sensors.get(channel_id, {}).copy()

        for key, sensor in sensors.items():
            readings[key] = sensor.read()

        return readings

    def read_all(self) -> Dict[int, Dict[str, SensorReading]]:
        all_readings: Dict[int, Dict[str, SensorReading]] = {}
        with self._lock:
            channel_ids = list(self._sensors.keys())

        for channel_id in channel_ids:
            all_readings[channel_id] = self.read_channel(channel_id)

        return all_readings

    def disconnect_all(self) -> None:
        with self._lock:
            for channel_sensors in self._sensors.values():
                for sensor in channel_sensors.values():
                    try:
                        sensor.disconnect()
                    except Exception as e:
                        logger.warning(f"断开传感器连接失败: {e}")
        self._sensors.clear()


sensor_manager = SensorManager()


def get_sensor_manager() -> SensorManager:
    return sensor_manager
