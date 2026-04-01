"""
单元测试 - 测试传感器、融合、采集、配置管理等模块
"""
import unittest
from datetime import datetime, timedelta
from typing import Optional
from unittest.mock import MagicMock, patch
import tempfile
import json
from pathlib import Path

from app.services.sampling import (
    check_drift_alarm,
    classify_status,
    fuse_sensor_values,
    load_config,
    reset_alarm_state,
)
from app.models.channel import AlarmType, Channel, ChannelStatus, SensorType
from app.models.liquid_level_data import DataStatus
from app.services.sensor import (
    MockSensor,
    SensorManager,
    SensorReading,
    SensorStatus,
    SensorType as ServiceSensorType,
)
from app.services.fusion import (
    FusionMethod,
    SensorFusion,
    WeightedAverageFusion,
    KalmanFilterFusion,
    MedianFusion,
    InsufficientDataError,
)
from app.services.config_manager import ConfigManager
from app.services.alarm import AlarmManager, AlarmType as ServiceAlarmType, AlarmLevel


class MockChannel:
    def __init__(
        self,
        id: int = 1,
        name: str = "测试通道",
        range_min: float = 0,
        range_max: float = 200,
        warning_low: float = 30,
        warning_high: float = 170,
        alarm_type: AlarmType = AlarmType.high,
        alarm_enabled: bool = True,
        sensor_type_a: SensorType = SensorType.capacitive,
        sensor_type_b: SensorType = SensorType.ultrasonic,
        calibration_offset_a: float = 0,
        calibration_offset_b: float = 0,
        fusion_weight_a: float = 0.5,
        fusion_weight_b: float = 0.5,
    ):
        self.id = id
        self.name = name
        self.range_min = range_min
        self.range_max = range_max
        self.warning_low = warning_low
        self.warning_high = warning_high
        self.alarm_type = alarm_type
        self.alarm_enabled = alarm_enabled
        self.sensor_type_a = sensor_type_a
        self.sensor_type_b = sensor_type_b
        self.calibration_offset_a = calibration_offset_a
        self.calibration_offset_b = calibration_offset_b
        self.fusion_weight_a = fusion_weight_a
        self.fusion_weight_b = fusion_weight_b


class TestSensorFusion(unittest.TestCase):
    """测试传感器融合逻辑"""

    def test_fuse_both_sensors(self):
        """测试双传感器融合"""
        result = fuse_sensor_values(100.0, 80.0, 0.6, 0.4)
        self.assertAlmostEqual(result, 92.0, places=2)

    def test_fuse_equal_weights(self):
        """测试等权重融合"""
        result = fuse_sensor_values(100.0, 80.0, 0.5, 0.5)
        self.assertAlmostEqual(result, 90.0, places=2)

    def test_fuse_only_sensor_a(self):
        """测试仅传感器A"""
        result = fuse_sensor_values(100.0, None, 0.5, 0.5)
        self.assertEqual(result, 100.0)

    def test_fuse_only_sensor_b(self):
        """测试仅传感器B"""
        result = fuse_sensor_values(None, 80.0, 0.5, 0.5)
        self.assertEqual(result, 80.0)

    def test_fuse_no_sensors(self):
        """测试无传感器数据"""
        with self.assertRaises(ValueError):
            fuse_sensor_values(None, None, 0.5, 0.5)


class TestStatusClassification(unittest.TestCase):
    """测试状态分类"""

    def setUp(self):
        self.channel = MockChannel()

    def test_normal_status(self):
        """测试正常状态"""
        status = classify_status(self.channel, 100.0)
        self.assertEqual(status, DataStatus.normal)

    def test_warning_low_status(self):
        """测试低于警告阈值"""
        status = classify_status(self.channel, 25.0)
        self.assertEqual(status, DataStatus.warning)

    def test_warning_high_status(self):
        """测试高于警告阈值"""
        status = classify_status(self.channel, 180.0)
        self.assertEqual(status, DataStatus.warning)

    def test_error_below_range(self):
        """测试低于量程"""
        status = classify_status(self.channel, -10.0)
        self.assertEqual(status, DataStatus.error)

    def test_error_above_range(self):
        """测试高于量程"""
        status = classify_status(self.channel, 250.0)
        self.assertEqual(status, DataStatus.error)


class TestDriftDetection(unittest.TestCase):
    """测试漂移检测"""

    def setUp(self):
        self.config = load_config()
        self.channel_id = 9999
        reset_alarm_state(self.channel_id)
        from app.services.sampling import _value_history
        _value_history[self.channel_id] = []

    def test_no_drift(self):
        """测试无漂移"""
        now = datetime.utcnow()
        from app.services.sampling import _value_history
        _value_history[self.channel_id] = []
        result = check_drift_alarm(self.channel_id, 100.0, now, self.config)
        self.assertFalse(result)

    def test_drift_detected(self):
        """测试检测到漂移（5秒内下降0.5mm）"""
        from app.services.sampling import _value_history
        _value_history[self.channel_id] = []
        
        now = datetime.utcnow()
        old_time = now - timedelta(seconds=5)
        
        check_drift_alarm(self.channel_id, 100.0, old_time, self.config)
        result = check_drift_alarm(self.channel_id, 99.4, now, self.config)
        
        self.assertTrue(result)

    def test_slow_drift_not_detected(self):
        """测试缓慢漂移不触发报警"""
        from app.services.sampling import _value_history
        _value_history[self.channel_id] = []
        
        now = datetime.utcnow()
        old_time = now - timedelta(seconds=5)
        
        check_drift_alarm(self.channel_id, 100.0, old_time, self.config)
        result = check_drift_alarm(self.channel_id, 99.6, now, self.config)
        
        self.assertFalse(result)


class TestConfigLoading(unittest.TestCase):
    """测试配置加载"""

    def test_load_config(self):
        """测试加载配置"""
        config = load_config()
        
        self.assertIn("alarm_consecutive_count", config)
        self.assertEqual(config["alarm_consecutive_count"], 3)
        
        self.assertIn("drift_detection", config)
        drift_config = config["drift_detection"]
        self.assertTrue(drift_config["enabled"])
        self.assertEqual(drift_config["window_seconds"], 5)
        self.assertEqual(drift_config["threshold_mm"], 0.5)


class TestMockSensor(unittest.TestCase):
    """测试模拟传感器"""

    def test_sensor_connect(self):
        """测试传感器连接"""
        sensor = MockSensor(
            channel_id=1,
            sensor_type=ServiceSensorType.capacitive,
        )
        self.assertTrue(sensor.connect())
        self.assertTrue(sensor.is_connected)

    def test_sensor_read(self):
        """测试传感器读取"""
        sensor = MockSensor(
            channel_id=1,
            sensor_type=ServiceSensorType.capacitive,
            initial_value=100.0,
        )
        sensor.connect()
        reading = sensor.read()
        
        self.assertEqual(reading.channel_id, 1)
        self.assertEqual(reading.status, SensorStatus.normal)
        self.assertIsNotNone(reading.value)
        self.assertAlmostEqual(reading.value, 100.0, delta=1.0)

    def test_sensor_calibration(self):
        """测试传感器校准"""
        sensor = MockSensor(
            channel_id=1,
            sensor_type=ServiceSensorType.capacitive,
            calibration_offset=10.0,
            initial_value=100.0,
        )
        sensor.connect()
        reading = sensor.read()
        
        self.assertAlmostEqual(reading.value, 110.0, delta=1.0)


class TestSensorManager(unittest.TestCase):
    """测试传感器管理器"""

    def test_register_sensor(self):
        """测试注册传感器"""
        manager = SensorManager()
        sensor = MockSensor(
            channel_id=1,
            sensor_type=ServiceSensorType.capacitive,
        )
        manager.register_sensor(1, "sensor_a", sensor)
        
        retrieved = manager.get_sensor(1, "sensor_a")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.channel_id, 1)

    def test_read_channel(self):
        """测试读取通道数据"""
        manager = SensorManager()
        sensor_a = MockSensor(
            channel_id=1,
            sensor_type=ServiceSensorType.capacitive,
            initial_value=100.0,
        )
        sensor_b = MockSensor(
            channel_id=1,
            sensor_type=ServiceSensorType.ultrasonic,
            initial_value=95.0,
        )
        
        manager.register_sensor(1, "sensor_a", sensor_a)
        manager.register_sensor(1, "sensor_b", sensor_b)
        
        readings = manager.read_channel(1)
        self.assertIn("sensor_a", readings)
        self.assertIn("sensor_b", readings)
        self.assertEqual(readings["sensor_a"].status, SensorStatus.normal)


class TestWeightedAverageFusion(unittest.TestCase):
    """测试加权平均融合"""

    def test_fuse_both_values(self):
        """测试双值融合"""
        fusion = WeightedAverageFusion(weight_a=0.6, weight_b=0.4)
        value, confidence, metadata = fusion.fuse(100.0, 80.0)
        
        self.assertAlmostEqual(value, 92.0, places=2)
        self.assertEqual(confidence, 1.0)
        self.assertEqual(metadata["sources"], 2)

    def test_fuse_single_value(self):
        """测试单值融合"""
        fusion = WeightedAverageFusion()
        value, confidence, metadata = fusion.fuse(100.0, None)
        
        self.assertEqual(value, 100.0)
        self.assertEqual(confidence, 0.7)
        self.assertEqual(metadata["sources"], 1)


class TestKalmanFilterFusion(unittest.TestCase):
    """测试卡尔曼滤波融合"""

    def test_kalman_initialization(self):
        """测试卡尔曼滤波初始化"""
        fusion = KalmanFilterFusion()
        value, confidence, metadata = fusion.fuse(100.0, None)
        
        self.assertEqual(value, 100.0)
        self.assertTrue(metadata.get("initialized", False))

    def test_kalman_fusion(self):
        """测试卡尔曼滤波融合"""
        fusion = KalmanFilterFusion()
        
        fusion.fuse(100.0, None)
        value, confidence, metadata = fusion.fuse(102.0, 98.0)
        
        self.assertIsNotNone(value)
        self.assertEqual(confidence, 1.0)


class TestMedianFusion(unittest.TestCase):
    """测试中值融合"""

    def test_median_fusion(self):
        """测试中值融合"""
        fusion = MedianFusion(history_size=3)
        
        fusion.fuse(100.0, 90.0)
        fusion.fuse(102.0, 88.0)
        value, confidence, metadata = fusion.fuse(98.0, 92.0)
        
        self.assertIsNotNone(value)
        self.assertGreater(confidence, 0)


class TestConfigManager(unittest.TestCase):
    """测试配置管理器"""

    def test_config_get(self):
        """测试配置获取"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.json"
            config_data = {
                "sampling_interval_ms": 100,
                "alarm_consecutive_count": 3,
            }
            
            with open(config_path, "w") as f:
                json.dump(config_data, f)
            
            manager = ConfigManager.__new__(ConfigManager)
            manager._initialized = False
            manager._config_path = config_path
            manager._config = {}
            manager._last_modified = None
            manager._callbacks = []
            manager._config_lock = MagicMock()
            manager._initialized = True
            manager._config = config_data
            
            self.assertEqual(manager.get("sampling_interval_ms"), 100)
            self.assertEqual(manager.get("alarm_consecutive_count"), 3)


class TestAlarmManager(unittest.TestCase):
    """测试报警管理器"""

    def setUp(self):
        self.manager = AlarmManager()

    def test_high_alarm(self):
        """测试高液位报警"""
        event = self.manager.check_high_alarm(
            channel_id=1,
            channel_name="测试通道",
            value=180.0,
            threshold=170.0,
            consecutive_count=1,
            value_a=180.0,
            value_b=None,
            sensor_source="sensor_a",
            sample_time=datetime.utcnow(),
        )
        
        self.assertIsNotNone(event)
        self.assertEqual(event.level, AlarmLevel.high)

    def test_low_alarm(self):
        """测试低液位报警"""
        event = self.manager.check_low_alarm(
            channel_id=1,
            channel_name="测试通道",
            value=20.0,
            threshold=30.0,
            consecutive_count=1,
            value_a=20.0,
            value_b=None,
            sensor_source="sensor_a",
            sample_time=datetime.utcnow(),
        )
        
        self.assertIsNotNone(event)
        self.assertEqual(event.level, AlarmLevel.low)

    def test_alarm_callback(self):
        """测试报警回调"""
        callback_called = []
        
        def callback(event):
            callback_called.append(event)
        
        self.manager.register_callback(callback)
        
        self.manager.check_high_alarm(
            channel_id=1,
            channel_name="测试通道",
            value=180.0,
            threshold=170.0,
            consecutive_count=1,
            value_a=180.0,
            value_b=None,
            sensor_source="sensor_a",
            sample_time=datetime.utcnow(),
        )
        
        self.assertEqual(len(callback_called), 1)


if __name__ == "__main__":
    unittest.main()
