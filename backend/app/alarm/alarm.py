import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

from app.fusion.fusion import FusionResult
from app.sensor.sensor import SensorData

logger = logging.getLogger(__name__)


class AlarmLevel(str, Enum):
    """报警级别"""
    INFO = "info"
    LOW = "low"
    HIGH = "high"
    CRITICAL = "critical"


class AlarmStatus(str, Enum):
    """报警状态"""
    ACTIVE = "active"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"


@dataclass
class AlarmRule:
    """报警规则"""
    channel_id: Optional[int]  # None 表示适用于所有通道
    level: AlarmLevel
    condition: str  # "<", ">", "==", "!=", "between"
    threshold_low: Optional[float] = None
    threshold_high: Optional[float] = None
    threshold_value: Optional[float] = None
    enabled: bool = True
    description: str = ""
    cooldown_seconds: int = 60  # 报警冷却时间

    def check(self, value: float) -> bool:
        """检查值是否触发报警"""
        if not self.enabled:
            return False

        if self.condition == "<":
            return self.threshold_value is not None and value < self.threshold_value
        elif self.condition == ">":
            return self.threshold_value is not None and value > self.threshold_value
        elif self.condition == "==":
            return self.threshold_value is not None and value == self.threshold_value
        elif self.condition == "!=":
            return self.threshold_value is not None and value != self.threshold_value
        elif self.condition == "between":
            return (self.threshold_low is not None and
                    self.threshold_high is not None and
                    self.threshold_low <= value <= self.threshold_high)
        return False


@dataclass
class AlarmEvent:
    """报警事件"""
    id: str
    channel_id: Optional[int]
    level: AlarmLevel
    message: str
    value: float
    threshold: Optional[float]
    occurred_at: datetime
    status: AlarmStatus = AlarmStatus.ACTIVE
    resolved_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "level": self.level.value,
            "message": self.message,
            "value": self.value,
            "threshold": self.threshold,
            "occurred_at": self.occurred_at.isoformat(),
            "status": self.status.value,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by,
        }


class AlarmManager:
    """报警管理器 - 负责报警检测、生成和管理"""

    def __init__(self):
        self._rules: list[AlarmRule] = []
        self._active_alarms: dict[str, AlarmEvent] = {}
        self._alarm_history: list[AlarmEvent] = []
        self._callbacks: list[Callable[[AlarmEvent], None]] = []
        self._lock = threading.Lock()
        self._last_alarm_time: dict[str, datetime] = {}
        self._history_limit = 1000

    def add_rule(self, rule: AlarmRule) -> None:
        """添加报警规则"""
        with self._lock:
            self._rules.append(rule)
            logger.info(f"报警规则已添加: {rule.description}")

    def remove_rule(self, rule: AlarmRule) -> None:
        """移除报警规则"""
        with self._lock:
            if rule in self._rules:
                self._rules.remove(rule)
                logger.info(f"报警规则已移除: {rule.description}")

    def clear_rules(self) -> None:
        """清除所有规则"""
        with self._lock:
            self._rules.clear()
            logger.info("所有报警规则已清除")

    def add_callback(self, callback: Callable[[AlarmEvent], None]) -> None:
        """添加报警回调"""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[AlarmEvent], None]) -> None:
        """移除报警回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _notify_callbacks(self, event: AlarmEvent) -> None:
        """通知所有回调"""
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"报警回调执行失败: {e}")

    def _generate_alarm_id(self, channel_id: Optional[int], level: AlarmLevel) -> str:
        """生成报警ID"""
        import uuid
        return f"{channel_id or 'all'}_{level.value}_{uuid.uuid4().hex[:8]}"

    def _check_cooldown(self, rule_key: str, cooldown_seconds: int) -> bool:
        """检查报警冷却时间"""
        now = datetime.utcnow()
        last_time = self._last_alarm_time.get(rule_key)

        if last_time is None:
            return True

        elapsed = (now - last_time).total_seconds()
        return elapsed >= cooldown_seconds

    def check_sensor_data(self, data: SensorData) -> list[AlarmEvent]:
        """检查传感器数据是否触发报警"""
        triggered_alarms = []

        with self._lock:
            for rule in self._rules:
                # 检查规则是否适用于该通道
                if rule.channel_id is not None and rule.channel_id != data.channel_id:
                    continue

                rule_key = f"{data.channel_id}_{rule.level.value}"

                if rule.check(data.value):
                    if not self._check_cooldown(rule_key, rule.cooldown_seconds):
                        continue

                    # 检查是否已有相同类型的活动报警
                    existing = any(
                        a.channel_id == data.channel_id and
                        a.level == rule.level and
                        a.status == AlarmStatus.ACTIVE
                        for a in self._active_alarms.values()
                    )

                    if not existing:
                        event = AlarmEvent(
                            id=self._generate_alarm_id(data.channel_id, rule.level),
                            channel_id=data.channel_id,
                            level=rule.level,
                            message=rule.description or f"通道 {data.channel_id} 触发 {rule.level.value} 级别报警",
                            value=data.value,
                            threshold=rule.threshold_value or rule.threshold_low or rule.threshold_high,
                            occurred_at=datetime.utcnow(),
                        )

                        self._active_alarms[event.id] = event
                        self._last_alarm_time[rule_key] = event.occurred_at
                        triggered_alarms.append(event)
                        self._notify_callbacks(event)

                        logger.warning(f"报警触发: {event.message}, 值: {data.value}")

        return triggered_alarms

    def check_fusion_result(self, result: FusionResult, channel_id: Optional[int] = None) -> list[AlarmEvent]:
        """检查融合结果是否触发报警"""
        triggered_alarms = []

        with self._lock:
            for rule in self._rules:
                if rule.channel_id is not None and rule.channel_id != channel_id:
                    continue

                rule_key = f"fusion_{channel_id or 'all'}_{rule.level.value}"

                if rule.check(result.fused_value):
                    if not self._check_cooldown(rule_key, rule.cooldown_seconds):
                        continue

                    existing = any(
                        a.channel_id == channel_id and
                        a.level == rule.level and
                        a.status == AlarmStatus.ACTIVE
                        for a in self._active_alarms.values()
                    )

                    if not existing:
                        event = AlarmEvent(
                            id=self._generate_alarm_id(channel_id, rule.level),
                            channel_id=channel_id,
                            level=rule.level,
                            message=rule.description or f"融合数据触发 {rule.level.value} 级别报警",
                            value=result.fused_value,
                            threshold=rule.threshold_value or rule.threshold_low or rule.threshold_high,
                            occurred_at=datetime.utcnow(),
                        )

                        self._active_alarms[event.id] = event
                        self._last_alarm_time[rule_key] = event.occurred_at
                        triggered_alarms.append(event)
                        self._notify_callbacks(event)

                        logger.warning(f"融合报警触发: {event.message}, 值: {result.fused_value}")

        return triggered_alarms

    def acknowledge_alarm(self, alarm_id: str, user: str) -> Optional[AlarmEvent]:
        """确认报警"""
        with self._lock:
            if alarm_id in self._active_alarms:
                alarm = self._active_alarms[alarm_id]
                alarm.status = AlarmStatus.ACKNOWLEDGED
                alarm.acknowledged_at = datetime.utcnow()
                alarm.acknowledged_by = user
                logger.info(f"报警已确认: {alarm_id}, 用户: {user}")
                return alarm
        return None

    def resolve_alarm(self, alarm_id: str) -> Optional[AlarmEvent]:
        """解决报警"""
        with self._lock:
            if alarm_id in self._active_alarms:
                alarm = self._active_alarms.pop(alarm_id)
                alarm.status = AlarmStatus.RESOLVED
                alarm.resolved_at = datetime.utcnow()
                self._alarm_history.append(alarm)

                # 限制历史记录大小
                if len(self._alarm_history) > self._history_limit:
                    self._alarm_history = self._alarm_history[-self._history_limit:]

                logger.info(f"报警已解决: {alarm_id}")
                return alarm
        return None

    def resolve_channel_alarms(self, channel_id: int) -> list[AlarmEvent]:
        """解决通道的所有报警"""
        resolved = []
        with self._lock:
            alarm_ids = [
                alarm_id for alarm_id, alarm in self._active_alarms.items()
                if alarm.channel_id == channel_id
            ]
            for alarm_id in alarm_ids:
                alarm = self.resolve_alarm(alarm_id)
                if alarm:
                    resolved.append(alarm)
        return resolved

    def get_active_alarms(self) -> list[AlarmEvent]:
        """获取所有活动报警"""
        with self._lock:
            return list(self._active_alarms.values())

    def get_alarm_history(self, limit: int = 100) -> list[AlarmEvent]:
        """获取报警历史"""
        with self._lock:
            return self._alarm_history[-limit:]

    def get_alarm_by_id(self, alarm_id: str) -> Optional[AlarmEvent]:
        """根据ID获取报警"""
        with self._lock:
            return self._active_alarms.get(alarm_id)

    def clear_all_alarms(self) -> None:
        """清除所有报警"""
        with self._lock:
            for alarm in self._active_alarms.values():
                alarm.status = AlarmStatus.RESOLVED
                alarm.resolved_at = datetime.utcnow()
                self._alarm_history.append(alarm)

            self._active_alarms.clear()

            if len(self._alarm_history) > self._history_limit:
                self._alarm_history = self._alarm_history[-self._history_limit:]

            logger.info("所有报警已清除")
