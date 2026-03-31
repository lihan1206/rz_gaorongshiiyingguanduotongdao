import logging
import statistics
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from app.sensor.sensor import SensorData

logger = logging.getLogger(__name__)


class FusionAlgorithm(str, Enum):
    """数据融合算法"""
    AVERAGE = "average"           # 简单平均
    WEIGHTED = "weighted"         # 加权平均
    MEDIAN = "median"             # 中位数
    KALMAN = "kalman"             # 卡尔曼滤波
    CONFIDENCE = "confidence"     # 置信度加权


@dataclass
class FusionResult:
    """融合结果"""
    fused_value: float
    confidence: float
    algorithm: FusionAlgorithm
    timestamp: datetime
    source_count: int
    std_deviation: Optional[float] = None
    details: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "fused_value": self.fused_value,
            "confidence": self.confidence,
            "algorithm": self.algorithm.value,
            "timestamp": self.timestamp.isoformat(),
            "source_count": self.source_count,
            "std_deviation": self.std_deviation,
            "details": self.details,
        }


class KalmanFilter:
    """简单卡尔曼滤波器"""

    def __init__(self, process_variance: float = 1e-5, measurement_variance: float = 1e-2):
        self.process_variance = process_variance
        self.measurement_variance = measurement_variance
        self.estimate = 0.0
        self.error_estimate = 1.0
        self.gain = 0.0

    def update(self, measurement: float) -> float:
        """更新滤波器并返回估计值"""
        # 预测
        prediction_error = self.error_estimate + self.process_variance

        # 更新
        self.gain = prediction_error / (prediction_error + self.measurement_variance)
        self.estimate = self.estimate + self.gain * (measurement - self.estimate)
        self.error_estimate = (1 - self.gain) * prediction_error

        return self.estimate

    def reset(self) -> None:
        """重置滤波器"""
        self.estimate = 0.0
        self.error_estimate = 1.0
        self.gain = 0.0


class DataFusion:
    """数据融合器 - 负责多传感器数据融合"""

    def __init__(self, algorithm: FusionAlgorithm = FusionAlgorithm.AVERAGE):
        self.algorithm = algorithm
        self._kalman_filters: dict[int, KalmanFilter] = {}
        self._weights: dict[int, float] = {}
        self._history: dict[int, list[float]] = {}
        self._max_history_size = 10

    def set_weights(self, weights: dict[int, float]) -> None:
        """设置通道权重（用于加权平均）"""
        total = sum(weights.values())
        if total > 0:
            self._weights = {k: v / total for k, v in weights.items()}
        else:
            self._weights = weights
        logger.debug(f"融合权重已更新: {self._weights}")

    def _get_kalman_filter(self, channel_id: int) -> KalmanFilter:
        """获取或创建卡尔曼滤波器"""
        if channel_id not in self._kalman_filters:
            self._kalman_filters[channel_id] = KalmanFilter()
        return self._kalman_filters[channel_id]

    def _update_history(self, channel_id: int, value: float) -> None:
        """更新历史数据"""
        if channel_id not in self._history:
            self._history[channel_id] = []
        self._history[channel_id].append(value)
        if len(self._history[channel_id]) > self._max_history_size:
            self._history[channel_id].pop(0)

    def _calculate_confidence(self, values: list[float], weights: Optional[list[float]] = None) -> float:
        """计算置信度"""
        if len(values) < 2:
            return 1.0

        try:
            std_dev = statistics.stdev(values)
            mean_val = statistics.mean(values)

            if mean_val == 0:
                return 1.0

            # 变异系数越小，置信度越高
            cv = std_dev / abs(mean_val)
            confidence = max(0.0, min(1.0, 1.0 - cv))
            return confidence
        except statistics.StatisticsError:
            return 1.0

    def fuse_average(self, data_list: list[SensorData]) -> FusionResult:
        """简单平均融合"""
        if not data_list:
            raise ValueError("数据列表为空")

        values = [d.value for d in data_list]
        fused_value = statistics.mean(values)
        confidence = self._calculate_confidence(values)

        return FusionResult(
            fused_value=fused_value,
            confidence=confidence,
            algorithm=FusionAlgorithm.AVERAGE,
            timestamp=datetime.utcnow(),
            source_count=len(data_list),
            std_deviation=statistics.stdev(values) if len(values) > 1 else 0.0,
        )

    def fuse_weighted(self, data_list: list[SensorData]) -> FusionResult:
        """加权平均融合"""
        if not data_list:
            raise ValueError("数据列表为空")

        total_weight = 0.0
        weighted_sum = 0.0
        used_weights = []

        for data in data_list:
            weight = self._weights.get(data.channel_id, 1.0 / len(data_list))
            weighted_sum += data.value * weight
            total_weight += weight
            used_weights.append(weight)

        fused_value = weighted_sum / total_weight if total_weight > 0 else weighted_sum

        values = [d.value for d in data_list]
        confidence = self._calculate_confidence(values, used_weights)

        return FusionResult(
            fused_value=fused_value,
            confidence=confidence,
            algorithm=FusionAlgorithm.WEIGHTED,
            timestamp=datetime.utcnow(),
            source_count=len(data_list),
            std_deviation=statistics.stdev(values) if len(values) > 1 else 0.0,
            details={"weights": used_weights},
        )

    def fuse_median(self, data_list: list[SensorData]) -> FusionResult:
        """中位数融合"""
        if not data_list:
            raise ValueError("数据列表为空")

        values = [d.value for d in data_list]
        fused_value = statistics.median(values)
        confidence = self._calculate_confidence(values)

        return FusionResult(
            fused_value=fused_value,
            confidence=confidence,
            algorithm=FusionAlgorithm.MEDIAN,
            timestamp=datetime.utcnow(),
            source_count=len(data_list),
            std_deviation=statistics.stdev(values) if len(values) > 1 else 0.0,
        )

    def fuse_kalman(self, data_list: list[SensorData]) -> FusionResult:
        """卡尔曼滤波融合"""
        if not data_list:
            raise ValueError("数据列表为空")

        filtered_values = []
        for data in data_list:
            kf = self._get_kalman_filter(data.channel_id)
            filtered_value = kf.update(data.value)
            filtered_values.append(filtered_value)
            self._update_history(data.channel_id, filtered_value)

        fused_value = statistics.mean(filtered_values)
        confidence = self._calculate_confidence(filtered_values)

        return FusionResult(
            fused_value=fused_value,
            confidence=confidence,
            algorithm=FusionAlgorithm.KALMAN,
            timestamp=datetime.utcnow(),
            source_count=len(data_list),
            std_deviation=statistics.stdev(filtered_values) if len(filtered_values) > 1 else 0.0,
        )

    def fuse_confidence(self, data_list: list[SensorData]) -> FusionResult:
        """置信度加权融合"""
        if not data_list:
            raise ValueError("数据列表为空")

        # 计算每个通道的历史标准差作为置信度依据
        confidences = []
        for data in data_list:
            self._update_history(data.channel_id, data.value)
            history = self._history.get(data.channel_id, [data.value])
            if len(history) > 1:
                try:
                    std_dev = statistics.stdev(history)
                    mean_val = statistics.mean(history)
                    cv = std_dev / abs(mean_val) if mean_val != 0 else 0
                    confidence = max(0.1, 1.0 - cv)  # 最小置信度0.1
                except statistics.StatisticsError:
                    confidence = 1.0
            else:
                confidence = 1.0
            confidences.append(confidence)

        # 使用置信度作为权重
        total_confidence = sum(confidences)
        if total_confidence == 0:
            total_confidence = 1.0

        weighted_sum = sum(
            data.value * conf / total_confidence
            for data, conf in zip(data_list, confidences)
        )

        values = [d.value for d in data_list]
        overall_confidence = self._calculate_confidence(values)

        return FusionResult(
            fused_value=weighted_sum,
            confidence=overall_confidence,
            algorithm=FusionAlgorithm.CONFIDENCE,
            timestamp=datetime.utcnow(),
            source_count=len(data_list),
            std_deviation=statistics.stdev(values) if len(values) > 1 else 0.0,
            details={"channel_confidences": confidences},
        )

    def fuse(self, data_list: list[SensorData]) -> FusionResult:
        """执行数据融合"""
        if not data_list:
            raise ValueError("数据列表为空")

        if len(data_list) == 1:
            # 单传感器直接返回
            return FusionResult(
                fused_value=data_list[0].value,
                confidence=1.0,
                algorithm=self.algorithm,
                timestamp=datetime.utcnow(),
                source_count=1,
            )

        logger.debug(f"执行数据融合: {self.algorithm.value}, 数据源数量: {len(data_list)}")

        if self.algorithm == FusionAlgorithm.AVERAGE:
            return self.fuse_average(data_list)
        elif self.algorithm == FusionAlgorithm.WEIGHTED:
            return self.fuse_weighted(data_list)
        elif self.algorithm == FusionAlgorithm.MEDIAN:
            return self.fuse_median(data_list)
        elif self.algorithm == FusionAlgorithm.KALMAN:
            return self.fuse_kalman(data_list)
        elif self.algorithm == FusionAlgorithm.CONFIDENCE:
            return self.fuse_confidence(data_list)
        else:
            raise ValueError(f"未知的融合算法: {self.algorithm}")

    def reset(self) -> None:
        """重置融合器状态"""
        self._kalman_filters.clear()
        self._history.clear()
        logger.info("数据融合器已重置")
