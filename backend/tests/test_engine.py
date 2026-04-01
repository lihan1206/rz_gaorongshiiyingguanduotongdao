"""
采集引擎单元测试
"""

import time
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from app.core.engine import (
    AcquisitionEngine,
    ChannelState,
    DataCollector,
    EngineStatus,
    EngineStats,
)
from app.sensor.sensor import SensorData


class TestEngineStats(unittest.TestCase):
    """测试引擎统计"""

    def test_initialization(self):
        """测试初始化"""
        stats = EngineStats()
        self.assertEqual(stats.total_samples, 0)
        self.assertEqual(stats.total_fusions, 0)
        self.assertEqual(stats.total_alarms, 0)
        self.assertEqual(stats.errors_count, 0)
        self.assertIsNone(stats.start_time)
        self.assertIsNone(stats.last_sample_time)


class TestChannelState(unittest.TestCase):
    """测试通道状态"""

    def test_initialization(self):
        """测试初始化"""
        state = ChannelState(channel_id=1)
        self.assertEqual(state.channel_id, 1)
        self.assertTrue(state.enabled)
        self.assertFalse(state.connected)
        self.assertIsNone(state.last_value)
        self.assertIsNone(state.last_timestamp)
        self.assertEqual(state.error_count, 0)
        self.assertEqual(state.sample_count, 0)


class TestAcquisitionEngine(unittest.TestCase):
    """测试采集引擎"""

    def setUp(self):
        """测试前准备"""
        # 使用模拟配置
        self.mock_config = Mock()
        self.mock_config.get_config.return_value = {
            "1": {"enabled": True, "port": "COM1", "baudrate": 9600, "sensor_type": "mock"},
            "2": {"enabled": True, "port": "COM2", "baudrate": 9600, "sensor_type": "mock"},
            "3": {"enabled": False, "port": "COM3", "baudrate": 9600, "sensor_type": "mock"},
            "4": {"enabled": True, "port": "COM4", "baudrate": 9600, "sensor_type": "mock"},
        }
        self.mock_config.get_system.return_value = Mock(
            sample_interval=0.1,
            fusion_algorithm="average",
        )

    def test_engine_initialization(self):
        """测试引擎初始化"""
        engine = AcquisitionEngine(config_manager=self.mock_config)
        self.assertEqual(engine.get_status(), EngineStatus.STOPPED)

    @patch('app.core.engine.ConfigManager')
    def test_engine_start_stop(self, mock_config_class):
        """测试引擎启动和停止"""
        mock_config = Mock()
        mock_config.get_config.return_value = {}
        mock_config.get_system.return_value = Mock(sample_interval=1.0, fusion_algorithm="average")
        mock_config_class.return_value = mock_config

        engine = AcquisitionEngine(config_manager=mock_config)

        # 启动引擎
        engine.start()
        self.assertEqual(engine.get_status(), EngineStatus.RUNNING)

        # 停止引擎
        engine.stop()
        self.assertEqual(engine.get_status(), EngineStatus.STOPPED)

    def test_engine_pause_resume(self):
        """测试引擎暂停和恢复"""
        engine = AcquisitionEngine(config_manager=self.mock_config)

        # 模拟启动状态
        engine._status = EngineStatus.RUNNING

        # 暂停
        engine.pause()
        self.assertEqual(engine.get_status(), EngineStatus.PAUSED)

        # 恢复
        engine.resume()
        self.assertEqual(engine.get_status(), EngineStatus.RUNNING)

    def test_get_stats(self):
        """测试获取统计信息"""
        engine = AcquisitionEngine(config_manager=self.mock_config)
        stats = engine.get_stats()

        self.assertIsInstance(stats, EngineStats)
        self.assertEqual(stats.total_samples, 0)

    def test_get_channel_states(self):
        """测试获取通道状态"""
        engine = AcquisitionEngine(config_manager=self.mock_config)
        states = engine.get_channel_states()

        self.assertIsInstance(states, dict)


class TestDataCollector(unittest.TestCase):
    """测试数据采集器"""

    def setUp(self):
        """测试前准备"""
        self.mock_config = Mock()
        self.mock_config.get_config.return_value = {
            "1": {"enabled": True, "port": "COM1", "baudrate": 9600, "sensor_type": "mock"},
            "2": {"enabled": True, "port": "COM2", "baudrate": 9600, "sensor_type": "mock"},
        }

    def test_collector_initialization(self):
        """测试采集器初始化"""
        collector = DataCollector(config_manager=self.mock_config)
        self.assertIsNotNone(collector)

    def test_add_remove_callback(self):
        """测试添加和移除回调"""
        collector = DataCollector(config_manager=self.mock_config)

        def test_callback(data):
            pass

        collector.add_callback(test_callback)
        self.assertIn(test_callback, collector._callbacks)

        collector.remove_callback(test_callback)
        self.assertNotIn(test_callback, collector._callbacks)

    def test_get_channel_states(self):
        """测试获取通道状态"""
        collector = DataCollector(config_manager=self.mock_config)
        states = collector.get_channel_states()
        self.assertIsInstance(states, dict)


class TestEngineIntegration(unittest.TestCase):
    """测试引擎集成"""

    @patch('app.core.engine.ConfigManager')
    @patch('app.core.engine.AlarmManager')
    def test_full_workflow(self, mock_alarm_class, mock_config_class):
        """测试完整工作流程"""
        # 设置模拟对象
        mock_config = Mock()
        mock_config.get_config.return_value = {
            "1": {"enabled": True, "port": "COM1", "baudrate": 9600, "sensor_type": "mock"},
        }
        mock_config.get_system.return_value = Mock(
            sample_interval=0.1,
            fusion_algorithm="average",
        )
        mock_config.get_threshold.return_value = Mock(
            warning_low=10.0,
            warning_high=90.0,
            critical_low=5.0,
            critical_high=95.0,
        )
        mock_config_class.return_value = mock_config

        mock_alarm = Mock()
        mock_alarm.check_sensor_data.return_value = []
        mock_alarm.check_fusion_result.return_value = []
        mock_alarm_class.return_value = mock_alarm

        # 创建引擎
        engine = AcquisitionEngine(
            config_manager=mock_config,
            alarm_manager=mock_alarm,
        )

        # 启动引擎
        engine.start()
        self.assertEqual(engine.get_status(), EngineStatus.RUNNING)

        # 等待一些数据采集
        time.sleep(0.5)

        # 获取统计
        stats = engine.get_stats()
        self.assertIsInstance(stats, EngineStats)

        # 停止引擎
        engine.stop()
        self.assertEqual(engine.get_status(), EngineStatus.STOPPED)


if __name__ == "__main__":
    unittest.main()
