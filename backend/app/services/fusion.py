import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class FusionMethod(str, Enum):
    weighted_average = "weighted_average"
    kalman_filter = "kalman_filter"
    median = "median"
    maximum = "maximum"
    minimum = "minimum"


class DataStatus(str, Enum):
    normal = "normal"
    warning = "warning"
    error = "error"


@dataclass
class FusionResult:
    fused_value: float
    status: DataStatus
    method: FusionMethod
    value_a: Optional[float]
    value_b: Optional[float]
    confidence: float
    timestamp: datetime
    metadata: Dict


class FusionError(Exception):
    pass


class InsufficientDataError(FusionError):
    pass


class BaseFusionStrategy(ABC):
    @abstractmethod
    def fuse(
        self,
        value_a: Optional[float],
        value_b: Optional[float],
        **kwargs,
    ) -> Tuple[float, float, Dict]:
        pass


class WeightedAverageFusion(BaseFusionStrategy):
    def __init__(self, weight_a: float = 0.5, weight_b: float = 0.5):
        self.weight_a = weight_a
        self.weight_b = weight_b

    def fuse(
        self,
        value_a: Optional[float],
        value_b: Optional[float],
        **kwargs,
    ) -> Tuple[float, float, Dict]:
        if value_a is not None and value_b is not None:
            fused = value_a * self.weight_a + value_b * self.weight_b
            confidence = 1.0
            metadata = {
                "sources": 2,
                "weight_a": self.weight_a,
                "weight_b": self.weight_b,
            }
        elif value_a is not None:
            fused = value_a
            confidence = 0.7
            metadata = {"sources": 1, "source": "sensor_a"}
        elif value_b is not None:
            fused = value_b
            confidence = 0.7
            metadata = {"sources": 1, "source": "sensor_b"}
        else:
            raise InsufficientDataError("至少需要一个传感器的值")

        return fused, confidence, metadata


class KalmanFilterFusion(BaseFusionStrategy):
    def __init__(
        self,
        process_noise: float = 0.01,
        measurement_noise_a: float = 0.1,
        measurement_noise_b: float = 0.1,
    ):
        self.process_noise = process_noise
        self.measurement_noise_a = measurement_noise_a
        self.measurement_noise_b = measurement_noise_b
        self._state: Optional[float] = None
        self._covariance: float = 1.0

    def fuse(
        self,
        value_a: Optional[float],
        value_b: Optional[float],
        **kwargs,
    ) -> Tuple[float, float, Dict]:
        if value_a is None and value_b is None:
            raise InsufficientDataError("至少需要一个传感器的值")

        if self._state is None:
            if value_a is not None:
                self._state = value_a
            else:
                self._state = value_b
            self._covariance = 1.0
            return self._state, 0.5, {"initialized": True}

        self._covariance += self.process_noise

        if value_a is not None and value_b is not None:
            kalman_a = self._covariance / (self._covariance + self.measurement_noise_a)
            kalman_b = self._covariance / (self._covariance + self.measurement_noise_b)

            total_kalman = kalman_a + kalman_b
            self._state = self._state + kalman_a * (value_a - self._state) + kalman_b * (value_b - self._state)
            self._covariance = (1 - total_kalman) * self._covariance

            confidence = 1.0
            metadata = {"sources": 2, "kalman_a": kalman_a, "kalman_b": kalman_b}
        elif value_a is not None:
            kalman = self._covariance / (self._covariance + self.measurement_noise_a)
            self._state = self._state + kalman * (value_a - self._state)
            self._covariance = (1 - kalman) * self._covariance

            confidence = 0.8
            metadata = {"sources": 1, "source": "sensor_a", "kalman": kalman}
        else:
            kalman = self._covariance / (self._covariance + self.measurement_noise_b)
            self._state = self._state + kalman * (value_b - self._state)
            self._covariance = (1 - kalman) * self._covariance

            confidence = 0.8
            metadata = {"sources": 1, "source": "sensor_b", "kalman": kalman}

        return self._state, confidence, metadata

    def reset(self) -> None:
        self._state = None
        self._covariance = 1.0


class MedianFusion(BaseFusionStrategy):
    def __init__(self, history_size: int = 5):
        self.history_size = history_size
        self._history_a: List[float] = []
        self._history_b: List[float] = []

    def fuse(
        self,
        value_a: Optional[float],
        value_b: Optional[float],
        **kwargs,
    ) -> Tuple[float, float, Dict]:
        if value_a is not None:
            self._history_a.append(value_a)
            if len(self._history_a) > self.history_size:
                self._history_a.pop(0)

        if value_b is not None:
            self._history_b.append(value_b)
            if len(self._history_b) > self.history_size:
                self._history_b.pop(0)

        all_values = self._history_a + self._history_b
        if not all_values:
            raise InsufficientDataError("至少需要一个传感器的值")

        sorted_values = sorted(all_values)
        n = len(sorted_values)
        if n % 2 == 0:
            fused = (sorted_values[n // 2 - 1] + sorted_values[n // 2]) / 2
        else:
            fused = sorted_values[n // 2]

        confidence = min(1.0, len(all_values) / (self.history_size * 2))
        metadata = {"samples": len(all_values), "history_size": self.history_size}

        return fused, confidence, metadata

    def reset(self) -> None:
        self._history_a.clear()
        self._history_b.clear()


class SensorFusion:
    def __init__(
        self,
        method: FusionMethod = FusionMethod.weighted_average,
        **fusion_params,
    ):
        self._method = method
        self._strategies: Dict[FusionMethod, BaseFusionStrategy] = {}
        self._current_strategy: Optional[BaseFusionStrategy] = None
        self._setup_strategy(method, **fusion_params)

    def _setup_strategy(self, method: FusionMethod, **params) -> None:
        if method == FusionMethod.weighted_average:
            strategy = WeightedAverageFusion(
                weight_a=params.get("weight_a", 0.5),
                weight_b=params.get("weight_b", 0.5),
            )
        elif method == FusionMethod.kalman_filter:
            strategy = KalmanFilterFusion(
                process_noise=params.get("process_noise", 0.01),
                measurement_noise_a=params.get("measurement_noise_a", 0.1),
                measurement_noise_b=params.get("measurement_noise_b", 0.1),
            )
        elif method == FusionMethod.median:
            strategy = MedianFusion(history_size=params.get("history_size", 5))
        else:
            strategy = WeightedAverageFusion()

        self._strategies[method] = strategy
        self._current_strategy = strategy
        self._method = method

    def set_method(self, method: FusionMethod, **params) -> None:
        if method in self._strategies:
            self._current_strategy = self._strategies[method]
        else:
            self._setup_strategy(method, **params)
        logger.info(f"融合方法切换为: {method.value}")

    def fuse(
        self,
        value_a: Optional[float],
        value_b: Optional[float],
        range_min: Optional[float] = None,
        range_max: Optional[float] = None,
        warning_low: Optional[float] = None,
        warning_high: Optional[float] = None,
    ) -> FusionResult:
        timestamp = datetime.utcnow()

        try:
            fused_value, confidence, metadata = self._current_strategy.fuse(
                value_a, value_b
            )

            if range_min is not None and fused_value < range_min:
                logger.warning(f"融合值 {fused_value} 低于最小范围 {range_min}")
            if range_max is not None and fused_value > range_max:
                logger.warning(f"融合值 {fused_value} 高于最大范围 {range_max}")

            status = self._classify_status(
                fused_value,
                range_min,
                range_max,
                warning_low,
                warning_high,
            )

            return FusionResult(
                fused_value=fused_value,
                status=status,
                method=self._method,
                value_a=value_a,
                value_b=value_b,
                confidence=confidence,
                timestamp=timestamp,
                metadata=metadata,
            )

        except InsufficientDataError as e:
            logger.error(f"融合失败: {e}")
            raise
        except Exception as e:
            logger.error(f"融合异常: {e}")
            raise FusionError(f"融合失败: {e}")

    def _classify_status(
        self,
        value: float,
        range_min: Optional[float],
        range_max: Optional[float],
        warning_low: Optional[float],
        warning_high: Optional[float],
    ) -> DataStatus:
        if range_min is not None and value < range_min:
            return DataStatus.error
        if range_max is not None and value > range_max:
            return DataStatus.error
        if warning_low is not None and value < warning_low:
            return DataStatus.warning
        if warning_high is not None and value > warning_high:
            return DataStatus.warning
        return DataStatus.normal

    def reset(self) -> None:
        for strategy in self._strategies.values():
            if hasattr(strategy, "reset"):
                strategy.reset()
        logger.info("融合状态已重置")


def fuse_sensor_values(
    value_a: Optional[float],
    value_b: Optional[float],
    weight_a: float = 0.5,
    weight_b: float = 0.5,
) -> float:
    if value_a is not None and value_b is not None:
        return value_a * weight_a + value_b * weight_b
    elif value_a is not None:
        return value_a
    elif value_b is not None:
        return value_b
    else:
        raise InsufficientDataError("至少需要一个传感器的值")


def classify_status(
    value: float,
    range_min: float,
    range_max: float,
    warning_low: float,
    warning_high: float,
) -> DataStatus:
    if value < range_min or value > range_max:
        return DataStatus.error
    if value < warning_low or value > warning_high:
        return DataStatus.warning
    return DataStatus.normal
