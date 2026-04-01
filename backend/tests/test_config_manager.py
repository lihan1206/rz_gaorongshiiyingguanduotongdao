"""
配置管理模块单元测试
"""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from app.config.config_manager import (
    ConfigManager,
    SensorConfig,
    SystemConfig,
    ThresholdConfig,
)


class TestConfigManager(unittest.TestCase):
    """测试配置管理器"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_manager = ConfigManager(
            config_dir=self.temp_dir,
            auto_reload=False,
        )

    def tearDown(self):
        """测试后清理"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_creates_default_configs(self):
        """测试初始化时创建默认配置文件"""
        self.assertTrue(Path(self.temp_dir).exists())
        self.assertTrue((Path(self.temp_dir) / "sensors.json").exists())
        self.assertTrue((Path(self.temp_dir) / "thresholds.json").exists())
        self.assertTrue((Path(self.temp_dir) / "system.json").exists())

    def test_load_and_get_threshold(self):
        """测试加载和获取阈值配置"""
        threshold = self.config_manager.get_threshold(1)
        self.assertIsNotNone(threshold)
        self.assertEqual(threshold.channel_id, 1)
        self.assertIsInstance(threshold.warning_low, float)
        self.assertIsInstance(threshold.warning_high, float)

    def test_set_and_get_sensor(self):
        """测试设置和获取传感器配置"""
        sensor = SensorConfig(
            channel_id=2,
            port="COM2",
            baudrate=115200,
            sensor_type="ultrasonic",
            enabled=True,
        )
        self.config_manager.set_sensor(sensor)

        retrieved = self.config_manager.get_sensor(2)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.channel_id, 2)
        self.assertEqual(retrieved.port, "COM2")
        self.assertEqual(retrieved.baudrate, 115200)

    def test_set_and_get_system_config(self):
        """测试设置和获取系统配置"""
        system = SystemConfig(
            sample_interval=2.0,
            fusion_algorithm="weighted",
            alarm_cooldown_seconds=120,
            data_retention_days=60,
            log_level="DEBUG",
        )
        self.config_manager.set_system(system)

        retrieved = self.config_manager.get_system()
        self.assertEqual(retrieved.sample_interval, 2.0)
        self.assertEqual(retrieved.fusion_algorithm, "weighted")
        self.assertEqual(retrieved.log_level, "DEBUG")

    def test_config_persistence(self):
        """测试配置持久化"""
        threshold = ThresholdConfig(
            channel_id=3,
            warning_low=20.0,
            warning_high=80.0,
            critical_low=10.0,
            critical_high=90.0,
        )
        self.config_manager.set_threshold(threshold)

        # 创建新的配置管理器实例，验证配置是否持久化
        new_manager = ConfigManager(
            config_dir=self.temp_dir,
            auto_reload=False,
        )
        retrieved = new_manager.get_threshold(3)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.warning_low, 20.0)
        self.assertEqual(retrieved.warning_high, 80.0)

    def test_config_callback(self):
        """测试配置变更回调"""
        callback_called = False
        callback_config_type = None

        def test_callback(config_type, config_data):
            nonlocal callback_called, callback_config_type
            callback_called = True
            callback_config_type = config_type

        self.config_manager.add_callback(test_callback)

        # 手动触发配置变更通知
        self.config_manager._notify_callbacks("system", {})

        self.assertTrue(callback_called)
        self.assertEqual(callback_config_type, "system")

    def test_invalid_json_handling(self):
        """测试无效JSON处理"""
        # 写入无效的JSON
        invalid_json_path = Path(self.temp_dir) / "sensors.json"
        with open(invalid_json_path, "w") as f:
            f.write("{invalid json}")

        # 应该能正常加载，使用默认配置
        manager = ConfigManager(
            config_dir=self.temp_dir,
            auto_reload=False,
        )
        # 不应该抛出异常
        self.assertIsNotNone(manager)


class TestConfigDataclasses(unittest.TestCase):
    """测试配置数据类"""

    def test_threshold_config_to_dict(self):
        """测试阈值配置转换为字典"""
        config = ThresholdConfig(
            channel_id=1,
            warning_low=10.0,
            warning_high=90.0,
        )
        data = config.to_dict()
        self.assertEqual(data["channel_id"], 1)
        self.assertEqual(data["warning_low"], 10.0)
        self.assertEqual(data["warning_high"], 90.0)

    def test_threshold_config_from_dict(self):
        """测试从字典创建阈值配置"""
        data = {
            "channel_id": 2,
            "warning_low": 15.0,
            "warning_high": 85.0,
            "critical_low": 5.0,
            "critical_high": 95.0,
            "range_min": 0.0,
            "range_max": 100.0,
            "alarm_enabled": True,
            "calibration_offset": 1.5,
        }
        config = ThresholdConfig.from_dict(data)
        self.assertEqual(config.channel_id, 2)
        self.assertEqual(config.calibration_offset, 1.5)

    def test_sensor_config_defaults(self):
        """测试传感器配置默认值"""
        config = SensorConfig(channel_id=1)
        self.assertEqual(config.port, "COM1")
        self.assertEqual(config.baudrate, 9600)
        self.assertEqual(config.sensor_type, "capacitive")
        self.assertTrue(config.enabled)

    def test_system_config_defaults(self):
        """测试系统配置默认值"""
        config = SystemConfig()
        self.assertEqual(config.sample_interval, 1.0)
        self.assertEqual(config.fusion_algorithm, "average")
        self.assertEqual(config.alarm_cooldown_seconds, 60)
        self.assertEqual(config.data_retention_days, 30)
        self.assertEqual(config.log_level, "INFO")


class TestConfigHotReload(unittest.TestCase):
    """测试配置热加载"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.callback_count = 0

        def callback(config_type, config_data):
            self.callback_count += 1

        self.config_manager = ConfigManager(
            config_dir=self.temp_dir,
            auto_reload=True,
            reload_interval=0.1,
        )
        self.config_manager.add_callback(callback)

        # 等待重载线程启动
        time.sleep(0.2)

    def tearDown(self):
        self.config_manager.stop_reload_thread()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_hot_reload(self):
        """测试配置热加载"""
        initial_count = self.callback_count

        # 修改配置文件
        system_file = Path(self.temp_dir) / "system.json"
        with open(system_file, "w") as f:
            json.dump({
                "sample_interval": 5.0,
                "fusion_algorithm": "kalman",
                "alarm_cooldown_seconds": 60,
                "data_retention_days": 30,
                "log_level": "INFO",
            }, f)

        # 等待重载
        time.sleep(0.3)

        # 验证配置已更新
        system = self.config_manager.get_system()
        self.assertEqual(system.sample_interval, 5.0)
        self.assertEqual(system.fusion_algorithm, "kalman")


if __name__ == "__main__":
    unittest.main()
