from typing import Any, Dict, Optional

from app.services.plugin import PluginInfo, PluginType, SensorPlugin
from app.services.sensor import BaseSensor, MockSensor, SensorType


class InfraredSensorPlugin(SensorPlugin):
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="infrared_sensor",
            version="1.0.0",
            plugin_type=PluginType.sensor,
            description="红外液位传感器插件",
            author="System",
        )

    def initialize(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.default_sensitivity = config.get("sensitivity", 1.0)

    def shutdown(self) -> None:
        pass

    def create_sensor(
        self,
        channel_id: int,
        sensor_type: SensorType,
        **kwargs,
    ) -> BaseSensor:
        sensitivity = kwargs.get("sensitivity", self.default_sensitivity)
        initial_value = kwargs.get("initial_value", 100.0)

        return MockSensor(
            channel_id=channel_id,
            sensor_type=sensor_type,
            calibration_offset=kwargs.get("calibration_offset", 0.0),
            initial_value=initial_value * sensitivity,
        )
