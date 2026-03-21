"""
API 测试脚本
测试多传感器融合、动态阈值调整和报警增强逻辑
"""
import json
import sys
import time
from datetime import datetime

import requests

BASE_URL = "http://localhost:8000"


def print_response(name: str, response: requests.Response):
    print(f"\n{'='*60}")
    print(f"[{name}]")
    print(f"状态码: {response.status_code}")
    try:
        data = response.json()
        print(f"响应: {json.dumps(data, ensure_ascii=False, indent=2, default=str)}")
    except Exception:
        print(f"响应: {response.text}")
    print('='*60)


def test_health():
    """测试健康检查"""
    response = requests.get(f"{BASE_URL}/health")
    print_response("健康检查", response)
    return response.status_code == 200


def test_list_channels():
    """测试获取通道列表"""
    response = requests.get(f"{BASE_URL}/channels")
    print_response("获取通道列表", response)
    return response.json() if response.status_code == 200 else []


def test_create_channel():
    """测试创建通道（双传感器配置）"""
    payload = {
        "name": "测试通道-双传感器",
        "sensor_type_a": "capacitive",
        "sensor_type_b": "ultrasonic",
        "range_min": 0,
        "range_max": 200,
        "unit": "mm",
        "calibration_offset_a": 0,
        "calibration_offset_b": 0,
        "fusion_weight_a": 0.6,
        "fusion_weight_b": 0.4,
        "warning_low": 30,
        "warning_high": 170,
        "alarm_type": "high",
        "alarm_enabled": True,
        "status": "active"
    }
    response = requests.post(f"{BASE_URL}/channels", json=payload)
    print_response("创建通道（双传感器配置）", response)
    return response.json() if response.status_code == 200 else None


def test_update_threshold(channel_id: int):
    """测试动态阈值调整"""
    payload = {
        "warning_low": 25,
        "warning_high": 175,
        "alarm_type": "high",
        "alarm_enabled": True
    }
    response = requests.post(f"{BASE_URL}/channels/thresholds/{channel_id}", json=payload)
    print_response(f"动态调整阈值 (通道 {channel_id})", response)
    return response.status_code == 200


def test_sync_samples(channel_id: int):
    """测试同步采样（双传感器数据融合）"""
    payload = {
        "sample_time": datetime.utcnow().isoformat(),
        "temperature": 25.5,
        "values": [
            {
                "channel_id": channel_id,
                "value_a": 100.5,
                "value_b": 98.2
            }
        ]
    }
    response = requests.post(f"{BASE_URL}/samples/sync", json=payload)
    print_response(f"同步采样（双传感器融合）- 通道 {channel_id}", response)
    return response.json() if response.status_code == 200 else None


def test_fusion_calculation(channel_id: int, weight_a: float, weight_b: float):
    """测试融合计算"""
    value_a = 100.0
    value_b = 80.0
    expected_fused = value_a * weight_a + value_b * weight_b
    
    payload = {
        "sample_time": datetime.utcnow().isoformat(),
        "values": [
            {
                "channel_id": channel_id,
                "value_a": value_a,
                "value_b": value_b
            }
        ]
    }
    response = requests.post(f"{BASE_URL}/samples/sync", json=payload)
    
    if response.status_code == 200:
        data = response.json()
        if data:
            actual_fused = data[0].get("fused_value")
            print(f"\n融合计算验证:")
            print(f"  传感器A值: {value_a}, 权重: {weight_a}")
            print(f"  传感器B值: {value_b}, 权重: {weight_b}")
            print(f"  期望融合值: {expected_fused}")
            print(f"  实际融合值: {actual_fused}")
            print(f"  计算正确: {abs(actual_fused - expected_fused) < 0.01}")
    
    return response.json() if response.status_code == 200 else None


def test_consecutive_alarm(channel_id: int, threshold_high: float):
    """测试连续3次超阈值报警"""
    print(f"\n{'#'*60}")
    print("# 测试连续3次超阈值报警逻辑")
    print(f"# 阈值上限: {threshold_high}")
    print('#'*60)
    
    over_threshold_value = threshold_high + 10
    
    for i in range(4):
        payload = {
            "sample_time": datetime.utcnow().isoformat(),
            "values": [
                {
                    "channel_id": channel_id,
                    "value_a": over_threshold_value,
                    "value_b": over_threshold_value
                }
            ]
        }
        response = requests.post(f"{BASE_URL}/samples/sync", json=payload)
        
        if response.status_code == 200:
            print(f"\n第 {i+1} 次采样 (值: {over_threshold_value})")
        
        time.sleep(0.1)
    
    response = requests.get(f"{BASE_URL}/alarms", params={"resolved": False})
    print_response("查询未解决报警", response)
    return response.json() if response.status_code == 200 else []


def test_drift_alarm(channel_id: int):
    """测试漂移报警"""
    print(f"\n{'#'*60}")
    print("# 测试漂移报警逻辑（5秒内下降0.5mm）")
    print('#'*60)
    
    start_value = 100.0
    
    for i in range(6):
        current_value = start_value - (i * 0.15)
        payload = {
            "sample_time": datetime.utcnow().isoformat(),
            "values": [
                {
                    "channel_id": channel_id,
                    "value_a": current_value,
                    "value_b": current_value
                }
            ]
        }
        response = requests.post(f"{BASE_URL}/samples/sync", json=payload)
        
        if response.status_code == 200:
            print(f"第 {i+1} 次采样 (值: {current_value:.2f}, 下降: {start_value - current_value:.2f}mm)")
        
        time.sleep(1)
    
    response = requests.get(f"{BASE_URL}/alarms", params={"resolved": False})
    alarms = response.json() if response.status_code == 200 else []
    
    drift_alarms = [a for a in alarms if a.get("level") == "drift"]
    print(f"\n检测到漂移报警数量: {len(drift_alarms)}")
    
    return drift_alarms


def test_resolve_alarm(alarm_id: int):
    """测试解决报警"""
    payload = {"resolved": True}
    response = requests.post(f"{BASE_URL}/alarms/{alarm_id}/resolve", json=payload)
    print_response(f"解决报警 {alarm_id}", response)
    return response.status_code == 200


def test_dashboard():
    """测试仪表盘"""
    response = requests.get(f"{BASE_URL}/dashboard/summary")
    print_response("仪表盘汇总", response)
    return response.json() if response.status_code == 200 else None


def test_samples_list(channel_id: int):
    """测试采样数据列表"""
    response = requests.get(f"{BASE_URL}/samples", params={"channel_id": channel_id, "limit": 10})
    print_response(f"采样数据列表 (通道 {channel_id})", response)
    return response.json() if response.status_code == 200 else []


def test_export_csv():
    """测试CSV导出"""
    response = requests.get(f"{BASE_URL}/samples/export")
    print_response("CSV导出", response)
    if response.status_code == 200:
        print(f"CSV内容预览:\n{response.text[:500]}...")
    return response.status_code == 200


def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*60)
    print("       高融石英管多通道液位检测系统 API 测试")
    print("="*60)
    
    if not test_health():
        print("\n❌ 服务未启动，请先运行: python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000")
        return False
    
    print("\n✅ 服务运行正常\n")
    
    channels = test_list_channels()
    
    if not channels:
        print("\n没有现有通道，创建新通道...")
        new_channel = test_create_channel()
        if new_channel:
            channels = [new_channel]
        else:
            print("❌ 创建通道失败")
            return False
    
    channel = channels[0]
    channel_id = channel["id"]
    weight_a = channel.get("fusion_weight_a", 0.5)
    weight_b = channel.get("fusion_weight_b", 0.5)
    
    test_update_threshold(channel_id)
    
    test_sync_samples(channel_id)
    
    test_fusion_calculation(channel_id, weight_a, weight_b)
    
    test_consecutive_alarm(channel_id, channel.get("warning_high", 170))
    
    test_samples_list(channel_id)
    
    test_dashboard()
    
    test_export_csv()
    
    print("\n" + "="*60)
    print("       测试完成")
    print("="*60)
    
    return True


if __name__ == "__main__":
    try:
        success = run_all_tests()
        sys.exit(0 if success else 1)
    except requests.exceptions.ConnectionError:
        print("\n❌ 无法连接到服务器")
        print("请先启动后端服务:")
        print("  cd backend && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
