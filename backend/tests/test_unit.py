"""
单元测试 - 测试传感器融合和报警逻辑
"""
import unittest
from datetime import datetime, timedelta
from typing import Optional

from app.services.sampling import (
    check_drift_alarm,
    classify_status,
    fuse_sensor_values,
    load_config,
    reset_alarm_state,
)
from app.models.channel import AlarmType, Channel, ChannelStatus, SensorType
from app.models.liquid_level_data import DataStatus


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


if __name__ == "__main__":
    unittest.main()
