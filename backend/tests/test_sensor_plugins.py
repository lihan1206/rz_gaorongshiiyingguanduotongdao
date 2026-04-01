"""
传感器插件系统单元测试
"""

import unittest
from datetime import datetime

from app.sensor.plugins import (
    BaseSensorDriver,
    SensorCapabilities,
    SensorPluginRegistry,
)
from app.sensor.plugins.mock_sensor import (
    MockSensorDriver,
    RandomSensorDriver,
    StepSensorDriver,
)


class TestSensorPluginRegistry(unittest.TestCase):
    """测试传感器插件注册表"""

    def setUp(self):
        """测试前准备"""
        # 保存原始状态
        self._original_drivers = SensorPluginRegistry._drivers.copy()

    def tearDown(self):
        """测试后恢复"""
        SensorPluginRegistry._drivers = self._original_drivers

    def test_register_driver(self):
        """测试注册驱动"""

        class TestDriver(BaseSensorDriver):
            @property
            def sensor_type(self):
                return "test"

            def connect(self):
                pass

            def disconnect(self):
                pass

            def read(self):
                return None

        SensorPluginRegistry.register("test_sensor", TestDriver)
        self.assertIn("test_sensor", SensorPluginRegistry.list_drivers())

    def test_unregister_driver(self):
        """测试注销驱动"""
        SensorPluginRegistry.unregister("test_sensor")
        self.assertNotIn("test_sensor", SensorPluginRegistry.list_drivers())

    def test_create_driver(self):
        """测试创建驱动实例"""
        driver = SensorPluginRegistry.create_driver(
            "mock",
            channel_id=1,
            config={"base_value": 50.0},
        )
        self.assertIsNotNone(driver)
        self.assertIsInstance(driver, MockSensorDriver)
        self.assertEqual(driver.channel_id, 1)

    def test_create_nonexistent_driver(self):
        """测试创建不存在的驱动"""
        driver = SensorPluginRegistry.create_driver(
            "nonexistent",
            channel_id=1,
            config={},
        )
        self.assertIsNone(driver)


class TestMockSensorDriver(unittest.TestCase):
    """测试模拟传感器驱动"""

    def setUp(self):
        """测试前准备"""
        self.config = {
            "base_value": 50.0,
            "amplitude": 10.0,
            "noise_level": 0.1,
            "frequency": 0.1,
        }
        self.driver = MockSensorDriver(channel_id=1, config=self.config)

    def test_initialization(self):
        """测试初始化"""
        self.assertEqual(self.driver.channel_id, 1)
        self.assertEqual(self.driver.sensor_type, "mock")
        self.assertFalse(self.driver.is_connected())

    def test_capabilities(self):
        """测试传感器能力"""
        caps = self.driver.capabilities
        self.assertIsInstance(caps, SensorCapabilities)
        self.assertTrue(caps.supports_temperature)
        self.assertEqual(caps.min_range, 0.0)
        self.assertEqual(caps.max_range, 100.0)

    def test_connect_disconnect(self):
        """测试连接和断开"""
        self.driver.connect()
        self.assertTrue(self.driver.is_connected())

        self.driver.disconnect()
        self.assertFalse(self.driver.is_connected())

    def test_read_without_connection(self):
        """测试未连接时读取"""
        data = self.driver.read()
        self.assertIsNone(data)

    def test_read_with_connection(self):
        """测试连接后读取"""
        self.driver.connect()
        data = self.driver.read()

        self.assertIsNotNone(data)
        self.assertEqual(data.channel_id, 1)
        self.assertIsNotNone(data.value)
        self.assertIsNotNone(data.timestamp)
        self.assertIsNotNone(data.temperature)

    def test_value_range(self):
        """测试值范围"""
        self.driver.connect()

        for _ in range(10):
            data = self.driver.read()
            self.assertGreaterEqual(data.value, 0.0)
            self.assertLessEqual(data.value, 100.0)


class TestRandomSensorDriver(unittest.TestCase):
    """测试随机传感器驱动"""

    def setUp(self):
        """测试前准备"""
        self.config = {
            "min_value": 20.0,
            "max_value": 80.0,
        }
        self.driver = RandomSensorDriver(channel_id=2, config=self.config)
        self.driver.connect()

    def test_value_in_range(self):
        """测试值在范围内"""
        for _ in range(20):
            data = self.driver.read()
            self.assertIsNotNone(data)
            self.assertGreaterEqual(data.value, 20.0)
            self.assertLessEqual(data.value, 80.0)

    def test_capabilities(self):
        """测试能力设置"""
        caps = self.driver.capabilities
        self.assertEqual(caps.min_range, 20.0)
        self.assertEqual(caps.max_range, 80.0)


class TestStepSensorDriver(unittest.TestCase):
    """测试阶梯传感器驱动"""

    def setUp(self):
        """测试前准备"""
        self.config = {
            "start_value": 50.0,
            "step_size": 5.0,
            "min_value": 0.0,
            "max_value": 100.0,
            "samples_per_step": 3,
        }
        self.driver = StepSensorDriver(channel_id=3, config=self.config)
        self.driver.connect()

    def test_step_behavior(self):
        """测试阶梯行为"""
        values = []
        for _ in range(12):  # 4个阶梯周期
            data = self.driver.read()
            values.append(data.value)

        # 第1-3个值应该相同（samples_per_step=3，第3次读取后计数器达到3）
        # 注意：第一次读取后计数器变为1，第3次读取后计数器变为3，触发阶梯变化
        # 所以 values[0], values[1] 相同，values[2] 可能是变化后的值
        self.assertEqual(values[0], values[1])

        # 检查阶梯变化发生（某些位置的值会不同）
        has_change = any(values[i] != values[i+1] for i in range(len(values)-1))
        self.assertTrue(has_change, "应该有阶梯变化发生")

    def test_boundary_behavior(self):
        """测试边界行为"""
        # 读取足够多的数据使其达到边界
        values = []
        for _ in range(100):
            data = self.driver.read()
            values.append(data.value)

        # 所有值都应该在范围内
        for value in values:
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 100.0)


class TestUltrasonicSensorDriver(unittest.TestCase):
    """测试超声波传感器驱动"""

    def test_distance_to_level_conversion(self):
        """测试距离到液位转换"""
        from app.sensor.plugins.ultrasonic_sensor import UltrasonicSensorDriver

        config = {
            "tank_height": 200.0,
            "empty_distance": 200.0,
        }
        driver = UltrasonicSensorDriver(channel_id=1, config=config)

        # 距离为0时，液位应该为200
        level = driver._distance_to_level(0.0)
        self.assertEqual(level, 200.0)

        # 距离为200时，液位应该为0
        level = driver._distance_to_level(200.0)
        self.assertEqual(level, 0.0)

        # 距离为100时，液位应该为100
        level = driver._distance_to_level(100.0)
        self.assertEqual(level, 100.0)

    def test_parse_json_data(self):
        """测试解析JSON数据"""
        from app.sensor.plugins.ultrasonic_sensor import UltrasonicSensorDriver

        driver = UltrasonicSensorDriver(channel_id=1, config={})

        # 测试JSON格式
        result = driver._parse_data('{"distance": 123.45, "temp": 25.0}')
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result[0], 123.45)
        self.assertAlmostEqual(result[1], 25.0)

    def test_parse_csv_data(self):
        """测试解析CSV数据"""
        from app.sensor.plugins.ultrasonic_sensor import UltrasonicSensorDriver

        driver = UltrasonicSensorDriver(channel_id=1, config={})

        # 测试CSV格式
        result = driver._parse_data("123.45, 25.0")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result[0], 123.45)
        self.assertAlmostEqual(result[1], 25.0)


class TestInfraredSensorDriver(unittest.TestCase):
    """测试红外传感器驱动"""

    def test_adc_to_distance_conversion(self):
        """测试ADC到距离转换"""
        from app.sensor.plugins.infrared_sensor import InfraredSensorDriver

        config = {
            "adc_resolution": 4096,
            "voltage_ref": 3.3,
        }
        driver = InfraredSensorDriver(channel_id=1, config=config)

        # ADC值为0时，电压为0，距离应该为最大值
        distance = driver._adc_to_distance(0)
        self.assertEqual(distance, 80.0)

    def test_parse_adc_data(self):
        """测试解析ADC数据"""
        from app.sensor.plugins.infrared_sensor import InfraredSensorDriver

        driver = InfraredSensorDriver(channel_id=1, config={})

        # 测试简单ADC值
        distance = driver._parse_data("2048")
        self.assertIsNotNone(distance)


class TestCapacitiveSensorDriver(unittest.TestCase):
    """测试电容式传感器驱动"""

    def test_capacitance_to_level_conversion(self):
        """测试电容值到液位转换"""
        from app.sensor.plugins.capacitive_sensor import CapacitiveSensorDriver

        config = {
            "empty_capacitance": 0.0,
            "full_capacitance": 1000.0,
        }
        driver = CapacitiveSensorDriver(channel_id=1, config=config)

        # 空罐时电容为0，液位为0%
        level = driver._capacitance_to_level(0.0)
        self.assertEqual(level, 0.0)

        # 满罐时电容为1000，液位为100%
        level = driver._capacitance_to_level(1000.0)
        self.assertEqual(level, 100.0)

        # 半罐时电容为500，液位为50%
        level = driver._capacitance_to_level(500.0)
        self.assertEqual(level, 50.0)

    def test_parse_level_data(self):
        """测试解析液位数据"""
        from app.sensor.plugins.capacitive_sensor import CapacitiveSensorDriver

        driver = CapacitiveSensorDriver(channel_id=1, config={})

        # 测试直接返回液位百分比
        result = driver._parse_data('{"level": 75.0}')
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result[0], 75.0)


if __name__ == "__main__":
    unittest.main()
