from typing import Any, Dict, Optional

from app.services.plugin import AlarmPlugin, PluginInfo, PluginType


class UltrasonicAlarmPlugin(AlarmPlugin):
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="ultrasonic_alarm",
            version="1.0.0",
            plugin_type=PluginType.alarm,
            description="超声波传感器专用报警插件",
        )

    def initialize(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.tolerance = config.get("tolerance", 5.0)

    def shutdown(self) -> None:
        pass

    def check_alarm(
        self,
        channel_id: int,
        value: float,
        threshold: float,
        **kwargs,
    ) -> bool:
        alarm_type = kwargs.get("alarm_type", "high")

        if alarm_type == "high":
            return value > threshold + self.tolerance
        elif alarm_type == "low":
            return value < threshold - self.tolerance

        return False
