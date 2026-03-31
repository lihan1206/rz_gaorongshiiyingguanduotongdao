import random
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SensorData:
    channel_id: int
    capacitive_value: float
    ultrasonic_value: float
    fused_value: float
    temperature: Optional[float] = None
    timestamp: datetime = None


class SensorError(Exception):
    """Base exception for sensor-related errors"""
    pass


class SerialPortError(SensorError):
    """Exception raised for serial port communication errors"""
    pass


class SensorReadError(SensorError):
    """Exception raised when sensor reading fails"""
    pass


class SensorSimulator:
    def __init__(self, base_value: float = 50.0, noise_level: float = 2.0):
        self.base_value = base_value
        self.noise_level = noise_level
        self.current_value = base_value
        self._drift_start = None
        self._drift_rate = 0.0

    def start_drift(self, rate: float = -0.1):
        self._drift_start = time.time()
        self._drift_rate = rate

    def stop_drift(self):
        self._drift_start = None

    def read_capacitive(self) -> float:
        try:
            noise = random.uniform(-self.noise_level, self.noise_level)
            drift = 0.0
            if self._drift_start:
                drift = self._drift_rate * (time.time() - self._drift_start)
            return max(0.0, min(100.0, self.current_value + noise + drift))
        except Exception as e:
            logger.error(f"电容传感器读取失败: {e}")
            raise SensorReadError(f"电容传感器读取失败: {e}") from e

    def read_ultrasonic(self) -> float:
        try:
            noise = random.uniform(-self.noise_level * 1.5, self.noise_level * 1.5)
            drift = 0.0
            if self._drift_start:
                drift = self._drift_rate * (time.time() - self._drift_start)
            return max(0.0, min(100.0, self.current_value + noise + drift))
        except Exception as e:
            logger.error(f"超声波传感器读取失败: {e}")
            raise SensorReadError(f"超声波传感器读取失败: {e}") from e


class SerialPortManager:
    def __init__(self, port: str = "/dev/ttyUSB0", baud_rate: int = 9600):
        self.port = port
        self.baud_rate = baud_rate
        self._is_connected = False
        self._serial = None

    def connect(self) -> bool:
        try:
            logger.info(f"尝试连接串口: {self.port}")
            self._is_connected = True
            logger.info(f"串口连接成功: {self.port}")
            return True
        except Exception as e:
            logger.error(f"串口连接失败: {e}")
            raise SerialPortError(f"无法连接到串口 {self.port}: {e}") from e

    def disconnect(self) -> None:
        self._is_connected = False
        logger.info(f"串口已断开: {self.port}")

    def is_connected(self) -> bool:
        return self._is_connected

    def read_data(self) -> bytes:
        if not self._is_connected:
            raise SerialPortError("串口未连接")
        try:
            return b""
        except Exception as e:
            logger.error(f"串口读取失败: {e}")
            raise SerialPortError(f"串口读取失败: {e}") from e


class SensorManager:
    def __init__(self, num_channels: int = 8, config: Optional[Dict] = None):
        self.num_channels = num_channels
        self.config = config or {}
        self.simulators: Dict[int, SensorSimulator] = {}
        self.kalman_state: Dict[int, tuple[float, float]] = {}
        self._initialize_sensors()

    def _initialize_sensors(self) -> None:
        try:
            for channel_id in range(1, self.num_channels + 1):
                self.simulators[channel_id] = SensorSimulator(
                    base_value=50.0 + random.uniform(-10, 10)
                )
                self.kalman_state[channel_id] = (50.0, 1.0)
            logger.info(f"已初始化 {self.num_channels} 个传感器通道")
        except Exception as e:
            logger.error(f"传感器初始化失败: {e}")
            raise SensorError(f"传感器初始化失败: {e}") from e

    def read_channel(self, channel_id: int, temperature: Optional[float] = None) -> SensorData:
        if channel_id not in self.simulators:
            logger.error(f"通道 {channel_id} 不存在")
            raise SensorError(f"通道 {channel_id} 不存在")

        try:
            simulator = self.simulators[channel_id]
            cap_value = simulator.read_capacitive()
            ult_value = simulator.read_ultrasonic()

            return SensorData(
                channel_id=channel_id,
                capacitive_value=round(cap_value, 3),
                ultrasonic_value=round(ult_value, 3),
                fused_value=0.0,
                temperature=temperature,
                timestamp=datetime.utcnow(),
            )
        except SensorReadError as e:
            logger.error(f"通道 {channel_id} 读取失败: {e}")
            raise
        except Exception as e:
            logger.error(f"通道 {channel_id} 读取发生未知错误: {e}")
            raise SensorError(f"通道 {channel_id} 读取失败: {e}") from e

    def read_all_channels(self, temperature: Optional[float] = None) -> List[SensorData]:
        sensor_data_list = []
        for channel_id in self.simulators.keys():
            try:
                data = self.read_channel(channel_id, temperature)
                sensor_data_list.append(data)
            except SensorError as e:
                logger.warning(f"跳过通道 {channel_id}: {e}")
                continue
        return sensor_data_list

    def update_kalman_state(self, channel_id: int, estimate: float, error: float) -> None:
        if channel_id in self.kalman_state:
            self.kalman_state[channel_id] = (estimate, error)

    def get_kalman_state(self, channel_id: int) -> Optional[tuple[float, float]]:
        return self.kalman_state.get(channel_id)

    def start_drift(self, channel_id: int, rate: float = -0.1) -> None:
        if channel_id in self.simulators:
            self.simulators[channel_id].start_drift(rate)
            logger.info(f"通道 {channel_id} 开始漂移模拟")

    def stop_drift(self, channel_id: int) -> None:
        if channel_id in self.simulators:
            self.simulators[channel_id].stop_drift()
            logger.info(f"通道 {channel_id} 停止漂移模拟")
