"""
告警模块单元测试
"""

import unittest
from datetime import datetime, timedelta

from app.alarm.alarm import (
    AlarmEvent,
    AlarmLevel,
    AlarmManager,
    AlarmRule,
    AlarmStatus,
)
from app.fusion.fusion import FusionResult, FusionAlgorithm
from app.sensor.sensor import SensorData


class TestAlarmRule(unittest.TestCase):
    """测试告警规则"""

    def test_less_than_condition(self):
        """测试小于条件"""
        rule = AlarmRule(
            channel_id=1,
            level=AlarmLevel.LOW,
            condition="<",
            threshold_value=10.0,
        )

        self.assertTrue(rule.check(5.0))
        self.assertFalse(rule.check(15.0))
        self.assertFalse(rule.check(10.0))

    def test_greater_than_condition(self):
        """测试大于条件"""
        rule = AlarmRule(
            channel_id=1,
            level=AlarmLevel.HIGH,
            condition=">",
            threshold_value=90.0,
        )

        self.assertTrue(rule.check(95.0))
        self.assertFalse(rule.check(85.0))
        self.assertFalse(rule.check(90.0))

    def test_between_condition(self):
        """测试区间条件"""
        rule = AlarmRule(
            channel_id=1,
            level=AlarmLevel.CRITICAL,
            condition="between",
            threshold_low=0.0,
            threshold_high=5.0,
        )

        self.assertTrue(rule.check(2.5))
        self.assertTrue(rule.check(0.0))
        self.assertTrue(rule.check(5.0))
        self.assertFalse(rule.check(6.0))
        self.assertFalse(rule.check(-1.0))

    def test_disabled_rule(self):
        """测试禁用规则"""
        rule = AlarmRule(
            channel_id=1,
            level=AlarmLevel.LOW,
            condition="<",
            threshold_value=10.0,
            enabled=False,
        )

        self.assertFalse(rule.check(5.0))

    def test_equal_condition(self):
        """测试等于条件"""
        rule = AlarmRule(
            channel_id=1,
            level=AlarmLevel.INFO,
            condition="==",
            threshold_value=50.0,
        )

        self.assertTrue(rule.check(50.0))
        self.assertFalse(rule.check(49.0))


class TestAlarmManager(unittest.TestCase):
    """测试告警管理器"""

    def setUp(self):
        """测试前准备"""
        self.manager = AlarmManager()
        self.test_rule = AlarmRule(
            channel_id=1,
            level=AlarmLevel.HIGH,
            condition=">",
            threshold_value=90.0,
            description="液位过高",
            cooldown_seconds=1,
        )
        self.manager.add_rule(self.test_rule)

    def test_add_rule(self):
        """测试添加规则"""
        self.assertEqual(len(self.manager._rules), 1)

    def test_check_sensor_data_triggers_alarm(self):
        """测试传感器数据触发告警"""
        data = SensorData(
            channel_id=1,
            value=95.0,
            timestamp=datetime.utcnow(),
        )
        alarms = self.manager.check_sensor_data(data)

        self.assertEqual(len(alarms), 1)
        self.assertEqual(alarms[0].level, AlarmLevel.HIGH)
        self.assertEqual(alarms[0].value, 95.0)

    def test_check_sensor_data_no_alarm(self):
        """测试传感器数据不触发告警"""
        data = SensorData(
            channel_id=1,
            value=80.0,
            timestamp=datetime.utcnow(),
        )
        alarms = self.manager.check_sensor_data(data)

        self.assertEqual(len(alarms), 0)

    def test_alarm_cooldown(self):
        """测试告警冷却"""
        data = SensorData(
            channel_id=1,
            value=95.0,
            timestamp=datetime.utcnow(),
        )

        # 第一次触发告警
        alarms1 = self.manager.check_sensor_data(data)
        self.assertEqual(len(alarms1), 1)

        # 冷却期内再次触发，不应产生新告警
        alarms2 = self.manager.check_sensor_data(data)
        self.assertEqual(len(alarms2), 0)

    def test_check_fusion_result(self):
        """测试融合结果告警检查"""
        result = FusionResult(
            fused_value=95.0,
            confidence=0.9,
            algorithm=FusionAlgorithm.AVERAGE,
            timestamp=datetime.utcnow(),
            source_count=3,
        )

        alarms = self.manager.check_fusion_result(result, channel_id=1)
        self.assertEqual(len(alarms), 1)

    def test_acknowledge_alarm(self):
        """测试确认告警"""
        data = SensorData(
            channel_id=1,
            value=95.0,
            timestamp=datetime.utcnow(),
        )
        alarms = self.manager.check_sensor_data(data)
        alarm_id = alarms[0].id

        acknowledged = self.manager.acknowledge_alarm(alarm_id, "admin")

        self.assertIsNotNone(acknowledged)
        self.assertEqual(acknowledged.status, AlarmStatus.ACKNOWLEDGED)
        self.assertEqual(acknowledged.acknowledged_by, "admin")

    def test_resolve_alarm(self):
        """测试解决告警"""
        data = SensorData(
            channel_id=1,
            value=95.0,
            timestamp=datetime.utcnow(),
        )
        alarms = self.manager.check_sensor_data(data)
        alarm_id = alarms[0].id

        resolved = self.manager.resolve_alarm(alarm_id)

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.status, AlarmStatus.RESOLVED)
        self.assertIsNotNone(resolved.resolved_at)

    def test_get_active_alarms(self):
        """测试获取活动告警"""
        data = SensorData(
            channel_id=1,
            value=95.0,
            timestamp=datetime.utcnow(),
        )
        self.manager.check_sensor_data(data)

        active_alarms = self.manager.get_active_alarms()
        self.assertEqual(len(active_alarms), 1)

    def test_clear_all_alarms(self):
        """测试清除所有告警"""
        data = SensorData(
            channel_id=1,
            value=95.0,
            timestamp=datetime.utcnow(),
        )
        self.manager.check_sensor_data(data)

        self.manager.clear_all_alarms()

        active_alarms = self.manager.get_active_alarms()
        self.assertEqual(len(active_alarms), 0)

    def test_alarm_event_serialization(self):
        """测试告警事件序列化"""
        event = AlarmEvent(
            id="test_123",
            channel_id=1,
            level=AlarmLevel.HIGH,
            message="测试告警",
            value=95.0,
            threshold=90.0,
            occurred_at=datetime.utcnow(),
        )

        data = event.to_dict()
        self.assertEqual(data["id"], "test_123")
        self.assertEqual(data["level"], "high")
        self.assertEqual(data["value"], 95.0)

    def test_global_rule(self):
        """测试全局规则（适用于所有通道）"""
        # 创建新的管理器，避免与setUp中的规则冲突
        manager = AlarmManager()

        global_rule = AlarmRule(
            channel_id=None,  # None表示适用于所有通道
            level=AlarmLevel.CRITICAL,
            condition=">",
            threshold_value=99.0,
        )
        manager.add_rule(global_rule)

        # 不同通道的数据都应该触发
        for channel_id in [1, 2, 3]:
            data = SensorData(
                channel_id=channel_id,
                value=99.5,
                timestamp=datetime.utcnow(),
            )
            alarms = manager.check_sensor_data(data)
            self.assertEqual(len(alarms), 1, f"通道 {channel_id} 应该触发告警")


class TestAlarmCallback(unittest.TestCase):
    """测试告警回调"""

    def test_callback_invocation(self):
        """测试回调调用"""
        manager = AlarmManager()
        callback_called = False
        received_event = None

        def test_callback(event):
            nonlocal callback_called, received_event
            callback_called = True
            received_event = event

        manager.add_callback(test_callback)

        rule = AlarmRule(
            channel_id=1,
            level=AlarmLevel.HIGH,
            condition=">",
            threshold_value=90.0,
        )
        manager.add_rule(rule)

        data = SensorData(
            channel_id=1,
            value=95.0,
            timestamp=datetime.utcnow(),
        )
        manager.check_sensor_data(data)

        self.assertTrue(callback_called)
        self.assertIsNotNone(received_event)
        self.assertEqual(received_event.level, AlarmLevel.HIGH)


if __name__ == "__main__":
    unittest.main()
