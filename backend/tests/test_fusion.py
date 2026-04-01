"""
数据融合模块单元测试
"""

import unittest
from datetime import datetime

from app.fusion.fusion import (
    DataFusion,
    FusionAlgorithm,
    FusionResult,
    KalmanFilter,
)
from app.sensor.sensor import SensorData


class TestKalmanFilter(unittest.TestCase):
    """测试卡尔曼滤波器"""

    def test_initialization(self):
        """测试初始化"""
        kf = KalmanFilter()
        self.assertEqual(kf.estimate, 0.0)
        self.assertEqual(kf.error_estimate, 1.0)

    def test_update(self):
        """测试滤波更新"""
        kf = KalmanFilter()

        # 连续更新应该收敛到测量值
        measurements = [10.0, 10.5, 9.8, 10.2, 10.1]
        for m in measurements:
            estimate = kf.update(m)

        # 估计值应该接近真实值
        self.assertAlmostEqual(kf.estimate, 10.0, delta=1.0)

    def test_noise_reduction(self):
        """测试噪声抑制"""
        kf = KalmanFilter(process_variance=1e-5, measurement_variance=1e-2)

        # 模拟带噪声的恒定信号
        true_value = 50.0
        noisy_measurements = [50.0 + i for i in [-2, 3, -1, 2, -3, 1, -2, 3]]

        estimates = []
        for m in noisy_measurements:
            estimates.append(kf.update(m))

        # 估计值的方差应该小于测量值的方差
        measurement_variance = sum((m - true_value) ** 2 for m in noisy_measurements) / len(noisy_measurements)
        estimate_variance = sum((e - true_value) ** 2 for e in estimates) / len(estimates)
        self.assertLess(estimate_variance, measurement_variance)

    def test_reset(self):
        """测试重置"""
        kf = KalmanFilter()
        kf.update(50.0)
        kf.update(60.0)

        kf.reset()
        self.assertEqual(kf.estimate, 0.0)
        self.assertEqual(kf.error_estimate, 1.0)


class TestDataFusion(unittest.TestCase):
    """测试数据融合"""

    def setUp(self):
        """测试前准备"""
        self.fusion = DataFusion(algorithm=FusionAlgorithm.AVERAGE)
        self.test_data = [
            SensorData(channel_id=1, value=50.0, timestamp=datetime.utcnow()),
            SensorData(channel_id=2, value=52.0, timestamp=datetime.utcnow()),
            SensorData(channel_id=3, value=48.0, timestamp=datetime.utcnow()),
        ]

    def test_average_fusion(self):
        """测试平均融合"""
        result = self.fusion.fuse_average(self.test_data)

        self.assertIsInstance(result, FusionResult)
        self.assertAlmostEqual(result.fused_value, 50.0, places=1)
        self.assertEqual(result.algorithm, FusionAlgorithm.AVERAGE)
        self.assertEqual(result.source_count, 3)

    def test_weighted_fusion(self):
        """测试加权融合"""
        weights = {1: 0.5, 2: 0.3, 3: 0.2}
        self.fusion.set_weights(weights)

        result = self.fusion.fuse_weighted(self.test_data)

        expected = 50.0 * 0.5 + 52.0 * 0.3 + 48.0 * 0.2
        self.assertAlmostEqual(result.fused_value, expected, places=1)
        self.assertEqual(result.algorithm, FusionAlgorithm.WEIGHTED)

    def test_median_fusion(self):
        """测试中位数融合"""
        result = self.fusion.fuse_median(self.test_data)

        self.assertAlmostEqual(result.fused_value, 50.0, places=1)
        self.assertEqual(result.algorithm, FusionAlgorithm.MEDIAN)

    def test_kalman_fusion(self):
        """测试卡尔曼滤波融合"""
        self.fusion.algorithm = FusionAlgorithm.KALMAN
        result = self.fusion.fuse(self.test_data)

        self.assertEqual(result.algorithm, FusionAlgorithm.KALMAN)
        self.assertEqual(result.source_count, 3)

    def test_confidence_fusion(self):
        """测试置信度融合"""
        result = self.fusion.fuse_confidence(self.test_data)

        self.assertEqual(result.algorithm, FusionAlgorithm.CONFIDENCE)
        self.assertIn("details", result.to_dict())

    def test_single_sensor_fusion(self):
        """测试单传感器融合"""
        single_data = [SensorData(channel_id=1, value=50.0, timestamp=datetime.utcnow())]
        result = self.fusion.fuse(single_data)

        self.assertEqual(result.fused_value, 50.0)
        self.assertEqual(result.confidence, 1.0)
        self.assertEqual(result.source_count, 1)

    def test_empty_data_fusion(self):
        """测试空数据融合"""
        with self.assertRaises(ValueError):
            self.fusion.fuse([])

    def test_confidence_calculation(self):
        """测试置信度计算"""
        # 高方差数据应该有较低置信度
        high_variance_data = [
            SensorData(channel_id=1, value=10.0, timestamp=datetime.utcnow()),
            SensorData(channel_id=2, value=90.0, timestamp=datetime.utcnow()),
        ]
        result = self.fusion.fuse_average(high_variance_data)

        # 高方差应该导致低置信度
        self.assertLess(result.confidence, 0.5)

        # 低方差数据应该有较高置信度
        low_variance_data = [
            SensorData(channel_id=1, value=49.0, timestamp=datetime.utcnow()),
            SensorData(channel_id=2, value=51.0, timestamp=datetime.utcnow()),
        ]
        result = self.fusion.fuse_average(low_variance_data)
        self.assertGreater(result.confidence, 0.8)

    def test_fusion_result_serialization(self):
        """测试融合结果序列化"""
        result = self.fusion.fuse_average(self.test_data)
        data = result.to_dict()

        self.assertIn("fused_value", data)
        self.assertIn("confidence", data)
        self.assertIn("algorithm", data)
        self.assertIn("timestamp", data)
        self.assertIn("source_count", data)

    def test_algorithm_switching(self):
        """测试算法切换"""
        self.fusion.algorithm = FusionAlgorithm.AVERAGE
        result1 = self.fusion.fuse(self.test_data)
        self.assertEqual(result1.algorithm, FusionAlgorithm.AVERAGE)

        self.fusion.algorithm = FusionAlgorithm.MEDIAN
        result2 = self.fusion.fuse(self.test_data)
        self.assertEqual(result2.algorithm, FusionAlgorithm.MEDIAN)

    def test_reset(self):
        """测试融合器重置"""
        self.fusion.fuse(self.test_data)
        self.fusion.reset()

        # 重置后历史应该被清空
        self.assertEqual(len(self.fusion._history), 0)
        self.assertEqual(len(self.fusion._kalman_filters), 0)


class TestFusionAlgorithmsComparison(unittest.TestCase):
    """比较不同融合算法的性能"""

    def setUp(self):
        """准备测试数据"""
        # 模拟带有异常值的数据
        self.data_with_outlier = [
            SensorData(channel_id=1, value=50.0, timestamp=datetime.utcnow()),
            SensorData(channel_id=2, value=51.0, timestamp=datetime.utcnow()),
            SensorData(channel_id=3, value=49.0, timestamp=datetime.utcnow()),
            SensorData(channel_id=4, value=80.0, timestamp=datetime.utcnow()),  # 异常值
        ]

    def test_median_robust_to_outliers(self):
        """测试中位数对异常值的鲁棒性"""
        fusion = DataFusion()

        avg_result = fusion.fuse_average(self.data_with_outlier)
        median_result = fusion.fuse_median(self.data_with_outlier)

        # 中位数应该更接近真实值
        true_value = 50.0
        avg_error = abs(avg_result.fused_value - true_value)
        median_error = abs(median_result.fused_value - true_value)

        self.assertLess(median_error, avg_error)


if __name__ == "__main__":
    unittest.main()
