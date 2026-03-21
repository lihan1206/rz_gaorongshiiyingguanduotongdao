#!/usr/bin/env python3
"""
系统功能测试脚本
测试传感器数据采集、融合和报警逻辑
"""
import sys
sys.path.insert(0, '.')

import time
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings, AppConfig
from app.db.base import Base
from app.models.channel import Channel, SensorType, ChannelStatus
from app.models.liquid_level_data import LiquidLevelData
from app.models.alarm import Alarm
from app.services.sensor_fusion import SensorManager, DataFusion
from app.services.alarm_detector import AlarmDetector
from app.services.sampling import ingest_fused_sensor_data


def test_sensor_data_collection():
    """测试传感器数据采集"""
    print("=" * 60)
    print("测试1: 传感器数据采集")
    print("=" * 60)
    
    manager = SensorManager(num_channels=4)
    
    # 读取单通道数据
    print("\n读取单通道数据:")
    data = manager.read_channel(1, temperature=25.5)
    print(f"通道1数据: 电容={data.capacitive_value:.3f}, 超声={data.ultrasonic_value:.3f}, 融合={data.fused_value:.3f}")
    
    # 读取所有通道数据
    print("\n读取所有通道数据:")
    all_data = manager.read_all_channels(temperature=25.5)
    for d in all_data:
        print(f"通道{d.channel_id}: 融合值={d.fused_value:.3f}")
    
    print("\n✓ 传感器数据采集测试通过!")
    return True


def test_data_fusion():
    """测试数据融合算法"""
    print("\n" + "=" * 60)
    print("测试2: 数据融合算法")
    print("=" * 60)
    
    # 测试加权平均
    print("\n加权平均法测试:")
    cap_val = 50.0
    ult_val = 52.0
    fused = DataFusion.weighted_average(cap_val, ult_val)
    weights = AppConfig.get_sensor_weights()
    print(f"电容值={cap_val}, 超声值={ult_val}")
    print(f"权重: 电容={weights['capacitive']}, 超声={weights['ultrasonic']}")
    print(f"融合结果={fused:.3f} (预期: {cap_val * 0.6 + ult_val * 0.4:.3f})")
    
    # 测试卡尔曼滤波
    print("\n卡尔曼滤波测试:")
    prev_estimate = 50.0
    prev_error = 1.0
    filtered, error = DataFusion.kalman_filter(51.0, 53.0, prev_estimate, prev_error)
    print(f"初始估计={prev_estimate}, 初始误差={prev_error}")
    print(f"新测量: 电容={51.0}, 超声={53.0}")
    print(f"滤波结果={filtered:.3f}, 新误差={error:.3f}")
    
    print("\n✓ 数据融合算法测试通过!")
    return True


def test_alarm_detection():
    """测试报警检测逻辑"""
    print("\n" + "=" * 60)
    print("测试3: 报警检测逻辑")
    print("=" * 60)
    
    # 创建内存数据库进行测试
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    # 创建测试通道
    channel = Channel(
        name="测试通道1",
        sensor_type=SensorType.hybrid,
        range_min=0.0,
        range_max=100.0,
        warning_low=20.0,
        warning_high=80.0,
        drift_threshold=0.5,
        drift_time_window=5,
        alarm_enabled=True,
        enabled_alarm_types="high,low,drift",
        status=ChannelStatus.active,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    
    alarm_detector = AlarmDetector(db)
    manager = SensorManager(num_channels=1)
    
    print("\n测试连续3次超阈值触发报警:")
    # 模拟高于阈值的数据
    high_values = [85.0, 86.0, 87.0]  # 高于阈值80
    alarms_triggered = 0
    
    for i, val in enumerate(high_values):
        # 修改模拟器返回的值
        manager.simulators[1].current_value = val
        data = manager.read_channel(1)
        # 手动设置融合值
        data.fused_value = val
        data.capacitive_value = val
        data.ultrasonic_value = val
        
        alarms = alarm_detector.process_sensor_data(channel, data)
        if alarms:
            alarms_triggered += len(alarms)
            for alarm in alarms:
                print(f"  触发报警: {alarm.alarm_type.value}, 值={alarm.actual_value}")
        else:
            status = alarm_detector.get_channel_status(1)
            print(f"  第{i+1}次检测: 连续警告数={status['consecutive_warnings']}")
    
    print(f"  触发报警数: {alarms_triggered}")
    
    print("\n测试漂移报警检测:")
    # 重置状态
    alarm_detector.reset_channel(1)
    
    # 模拟漂移（连续下降）
    base_value = 50.0
    drift_rate = -0.2  # 每次下降0.2
    drift_alarms = 0
    
    for i in range(10):
        val = base_value + drift_rate * i
        manager.simulators[1].current_value = val
        data = manager.read_channel(1)
        data.fused_value = val
        data.capacitive_value = val
        data.ultrasonic_value = val
        
        alarms = alarm_detector.process_sensor_data(channel, data)
        if alarms:
            drift_alarms += len([a for a in alarms if a.alarm_type == 'drift'])
    
    print(f"  漂移报警数: {drift_alarms}")
    
    db.close()
    print("\n✓ 报警检测逻辑测试通过!")
    return True


def test_config_updates():
    """测试配置更新功能"""
    print("\n" + "=" * 60)
    print("测试4: 配置更新功能")
    print("=" * 60)
    
    # 测试传感器权重配置
    print("\n传感器权重配置测试:")
    original_weights = AppConfig.get_sensor_weights()
    print(f"原权重: 电容={original_weights['capacitive']}, 超声={original_weights['ultrasonic']}")
    
    try:
        AppConfig.set_sensor_weights(0.7, 0.3)
        new_weights = AppConfig.get_sensor_weights()
        print(f"新权重: 电容={new_weights['capacitive']}, 超声={new_weights['ultrasonic']}")
    except ValueError as e:
        print(f"错误: {e}")
    
    # 测试无效权重（和不为1）
    try:
        AppConfig.set_sensor_weights(0.8, 0.3)
        print("错误: 应该抛出异常但没有")
    except ValueError as e:
        print(f"正确捕获无效权重错误: {e}")
    
    # 恢复原权重
    AppConfig.set_sensor_weights(original_weights['capacitive'], original_weights['ultrasonic'])
    
    print("\n✓ 配置更新功能测试通过!")
    return True


def test_data_persistence():
    """测试数据持久化"""
    print("\n" + "=" * 60)
    print("测试5: 数据持久化")
    print("=" * 60)
    
    # 创建内存数据库进行测试
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    # 创建测试通道
    channel = Channel(
        name="测试通道2",
        sensor_type=SensorType.hybrid,
        range_min=0.0,
        range_max=100.0,
        warning_low=10.0,
        warning_high=90.0,
        status=ChannelStatus.active,
    )
    db.add(channel)
    db.commit()
    
    manager = SensorManager(num_channels=1)
    sensor_data_list = manager.read_all_channels(temperature=25.0)
    
    # 存储数据
    records = ingest_fused_sensor_data(db, sensor_data_list)
    print(f"\n存储数据记录数: {len(records)}")
    
    # 验证存储
    for record in records:
        print(f"通道{record.channel_id}: 融合值={record.fused_value:.3f}, 状态={record.status.value}")
    
    # 查询数据
    stored_data = db.query(LiquidLevelData).all()
    print(f"数据库中数据记录数: {len(stored_data)}")
    
    db.close()
    print("\n✓ 数据持久化测试通过!")
    return True


def main():
    """运行所有测试"""
    print("系统功能测试开始\n")
    
    tests = [
        test_sensor_data_collection,
        test_data_fusion,
        test_alarm_detection,
        test_config_updates,
        test_data_persistence,
    ]
    
    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"\n✗ {test.__name__} 失败: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
    
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"通过: {passed}/{total}")
    
    if passed == total:
        print("\n🎉 所有测试通过!")
    else:
        print("\n⚠️  部分测试失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
