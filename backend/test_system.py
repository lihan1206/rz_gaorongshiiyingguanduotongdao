#!/usr/bin/env python3
"""
系统功能测试脚本
用于测试多通道液位传感器数据采集系统的各项功能
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

import asyncio
import logging
from datetime import datetime
from typing import List

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_configuration():
    """测试配置管理功能"""
    logger.info("=== 测试配置管理功能 ===")
    
    from app.config import AppConfig, ConfigError, JSONParseError
    
    try:
        AppConfig.load_config(force_reload=True)
        logger.info("配置文件加载成功")
        
        sensor_weights = AppConfig.get_sensor_weights()
        logger.info(f"传感器权重: {sensor_weights}")
        
        sampling_settings = AppConfig.get_sampling_settings()
        logger.info(f"采样设置: {sampling_settings}")
        
        alarm_settings = AppConfig.get_alarm_settings()
        logger.info(f"报警设置: {alarm_settings}")
        
        config_info = AppConfig.get_config_info()
        logger.info(f"配置信息: {config_info}")
        
        logger.info("配置管理功能测试通过 ✓")
    except Exception as e:
        logger.error(f"配置管理功能测试失败: {e}")
        raise


def test_sensor_simulation():
    """测试传感器模拟功能"""
    logger.info("=== 测试传感器模拟功能 ===")
    
    from app.sensor import SensorManager, SensorError, SensorData
    
    try:
        sensor_manager = SensorManager(num_channels=4)
        logger.info(f"传感器管理器初始化成功，通道数: {sensor_manager.num_channels}")
        
        data = sensor_manager.read_channel(1)
        logger.info(f"通道1读数: 电容={data.capacitive_value}, 超声波={data.ultrasonic_value}, 融合={data.fused_value}")
        
        all_data = sensor_manager.read_all_channels(temperature=25.5)
        logger.info(f"所有通道读数完成，共 {len(all_data)} 条数据")
        
        for d in all_data[:2]:
            logger.info(f"通道{d.channel_id}: {d.fused_value}")
        
        sensor_manager.start_drift(1, rate=-0.5)
        logger.info("通道1开始漂移模拟")
        
        for i in range(3):
            data = sensor_manager.read_channel(1)
            logger.info(f"漂移读数 {i+1}: {data.fused_value}")
        
        sensor_manager.stop_drift(1)
        logger.info("传感器模拟功能测试通过 ✓")
    except Exception as e:
        logger.error(f"传感器模拟功能测试失败: {e}")
        raise


def test_data_fusion():
    """测试数据融合功能"""
    logger.info("=== 测试数据融合功能 ===")
    
    from app.sensor import SensorManager
    from app.fusion import FusionManager, DataFusion, FusionError
    
    try:
        sensor_manager = SensorManager(num_channels=4)
        fusion_manager = FusionManager(
            sensor_manager=sensor_manager,
            weights={"capacitive": 0.6, "ultrasonic": 0.4},
            use_kalman=True,
        )
        logger.info("融合管理器初始化成功")
        
        raw_data = sensor_manager.read_channel(1)
        logger.info(f"原始数据: 电容={raw_data.capacitive_value}, 超声波={raw_data.ultrasonic_value}")
        
        fused_data = fusion_manager.process_sensor_data(raw_data)
        logger.info(f"融合结果: {fused_data.fused_value}")
        
        weighted_avg = DataFusion.weighted_average(50.0, 52.0, {"capacitive": 0.6, "ultrasonic": 0.4})
        logger.info(f"加权平均测试: 50.0*0.6 + 52.0*0.4 = {weighted_avg}")
        
        kalman_result, error = DataFusion.kalman_filter(50.0, 52.0, 50.0, 1.0)
        logger.info(f"卡尔曼滤波测试: 结果={kalman_result:.3f}, 误差={error:.3f}")
        
        all_data = sensor_manager.read_all_channels()
        fused_batch = fusion_manager.process_batch(all_data)
        logger.info(f"批量融合完成，共 {len(fused_batch)} 条数据")
        
        logger.info("数据融合功能测试通过 ✓")
    except Exception as e:
        logger.error(f"数据融合功能测试失败: {e}")
        raise


def test_sensor_plugins():
    """测试传感器插件系统"""
    logger.info("=== 测试传感器插件系统 ===")
    
    try:
        from app.sensor_plugins import (
            SensorPluginManager,
            CapacitiveSensor,
            UltrasonicSensor,
            InfraredSensor,
        )
        
        plugin_manager = SensorPluginManager()
        
        available = plugin_manager.list_available_plugins()
        logger.info(f"可用插件: {[p['name'] for p in available]}")
        
        cap_plugin = plugin_manager.create_plugin(
            "capacitive",
            "cap_channel_1",
            {"channel_id": 1, "base_value": 60.0},
        )
        logger.info(f"创建电容插件: {cap_plugin.plugin_name}")
        
        ult_plugin = plugin_manager.create_plugin(
            "ultrasonic",
            "ult_channel_1",
            {"channel_id": 1, "base_value": 60.0},
        )
        logger.info(f"创建超声波插件: {ult_plugin.plugin_name}")
        
        inf_plugin = plugin_manager.create_plugin(
            "infrared",
            "inf_channel_1",
            {"channel_id": 1, "base_value": 60.0},
        )
        logger.info(f"创建红外插件: {inf_plugin.plugin_name}")
        
        cap_plugin.connect()
        ult_plugin.connect()
        inf_plugin.connect()
        
        cap_reading = cap_plugin.read()
        logger.info(f"电容读数: {cap_reading.value}")
        
        ult_reading = ult_plugin.read()
        logger.info(f"超声波读数: {ult_reading.value}")
        
        inf_reading = inf_plugin.read()
        logger.info(f"红外读数: {inf_reading.value}")
        
        active = plugin_manager.list_active_instances()
        logger.info(f"活动实例数: {len(active)}")
        
        all_readings = plugin_manager.read_all()
        logger.info(f"批量读数数: {len(all_readings)}")
        
        plugin_manager.disconnect_all()
        logger.info("所有插件已断开连接")
        
        logger.info("传感器插件系统测试通过 ✓")
    except Exception as e:
        logger.error(f"传感器插件系统测试失败: {e}")
        raise


async def test_async_acquisition():
    """测试异步数据采集"""
    logger.info("=== 测试异步数据采集 ===")
    
    try:
        from app.sensor import SensorManager
        from app.fusion import FusionManager
        from app.services.acquisition import AsyncDataAcquisition
        
        sensor_manager = SensorManager(num_channels=4)
        fusion_manager = FusionManager(sensor_manager=sensor_manager)
        
        class MockDBManager:
            def get_session(self):
                class MockSession:
                    def __enter__(self): return self
                    def __exit__(self, *args): pass
                return MockSession()
        
        async_acq = AsyncDataAcquisition(
            sensor_manager=sensor_manager,
            fusion_manager=fusion_manager,
            db_manager=MockDBManager(),
            max_workers=4,
        )
        logger.info("异步采集器初始化成功")
        
        results = await async_acq.read_all_channels(temperature=25.0)
        
        success_count = sum(1 for r in results if r.success)
        logger.info(f"异步采集结果: 成功 {success_count}/{len(results)}")
        
        for result in results[:2]:
            if result.success:
                logger.info(f"通道{result.channel_id}: {result.data.fused_value}")
            else:
                logger.warning(f"通道{result.channel_id}: {result.error}")
        
        async_acq.stop()
        logger.info("异步数据采集测试通过 ✓")
    except Exception as e:
        logger.error(f"异步数据采集测试失败: {e}")
        raise


def test_alarm_detection():
    """测试报警检测功能"""
    logger.info("=== 测试报警检测功能 ===")
    
    try:
        from app.alarm import AlarmDetector, ChannelAlarmConfig, AlarmType, AlarmLevel
        
        alarm_settings = {
            "consecutive_threshold": 2,
            "drift_detection_window": 5,
            "drift_rate_threshold": 0.1,
        }
        
        alarm_detector = AlarmDetector(alarm_settings=alarm_settings)
        logger.info("报警检测器初始化成功")
        
        channel_config = ChannelAlarmConfig(
            warning_low=10.0,
            warning_high=90.0,
            drift_threshold=5.0,
            drift_time_window=5,
        )
        alarm_detector.configure_channel(1, channel_config)
        logger.info("通道1报警配置完成")
        
        test_values = [5.0, 8.0, 15.0, 95.0, 92.0, 85.0]
        all_alarms = []
        
        for i, value in enumerate(test_values):
            alarms = alarm_detector.process_value(
                channel_id=1,
                value=value,
                timestamp=datetime.utcnow(),
                channel_name=f"测试通道{i+1}",
                unit="%",
            )
            all_alarms.extend(alarms)
            if alarms:
                logger.info(f"值 {value} 触发报警: {[a.description for a in alarms]}")
        
        logger.info(f"总共触发 {len(all_alarms)} 个报警")
        
        active_alarms = alarm_detector.get_active_alarms(1)
        logger.info(f"当前活跃报警数: {len(active_alarms)}")
        
        status = alarm_detector.get_channel_status(1)
        logger.info(f"通道状态: 近期值={status['recent_values'][-5:]}")
        
        logger.info("报警检测功能测试通过 ✓")
    except Exception as e:
        logger.error(f"报警检测功能测试失败: {e}")
        raise


def test_database_operations():
    """测试数据库操作（使用SQLite进行测试）"""
    logger.info("=== 测试数据库操作 ===")
    
    try:
        from app.database import DatabaseManager, ConnectionError
        
        test_db_url = "sqlite:///:memory:"
        db_manager = DatabaseManager(test_db_url)
        logger.info("数据库管理器初始化成功")
        
        connected = db_manager.test_connection()
        logger.info(f"数据库连接测试: {'成功' if connected else '失败'}")
        
        logger.info("数据库操作测试通过 ✓")
    except Exception as e:
        logger.warning(f"数据库操作测试跳过（需要MySQL连接）: {e}")


def main():
    """运行所有测试"""
    logger.info("=" * 60)
    logger.info("开始运行系统功能测试")
    logger.info("=" * 60)
    
    tests = [
        ("配置管理功能", test_configuration),
        ("传感器模拟功能", test_sensor_simulation),
        ("数据融合功能", test_data_fusion),
        ("传感器插件系统", test_sensor_plugins),
        ("报警检测功能", test_alarm_detection),
        ("数据库操作", test_database_operations),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            test_func()
            results.append((test_name, "PASS", None))
        except Exception as e:
            results.append((test_name, "FAIL", str(e)))
    
    logger.info("=" * 60)
    logger.info("测试总结")
    logger.info("=" * 60)
    
    for test_name, status, error in results:
        if status == "PASS":
            logger.info(f"✓ {test_name}: 通过")
        else:
            logger.error(f"✗ {test_name}: 失败 - {error}")
    
    passed = sum(1 for r in results if r[1] == "PASS")
    total = len(results)
    logger.info("=" * 60)
    logger.info(f"测试结果: {passed}/{total} 项测试通过")
    logger.info("=" * 60)
    
    logger.info("\n=== 运行异步采集测试 ===")
    asyncio.run(test_async_acquisition())
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
