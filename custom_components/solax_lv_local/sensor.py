"""Sensors for the SolaX LV Local integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SolaxConfigEntry
from .const import DEV_INVERTER
from .entity import SolaxEntity
from .registers import SENSORS, Reg, decode


async def async_setup_entry(
    hass: HomeAssistant, entry: SolaxConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [SolaxSensor(coordinator, reg) for reg in SENSORS]
    entities.append(PvTotalSensor(coordinator))
    async_add_entities(entities)


class SolaxSensor(SolaxEntity, SensorEntity):
    def __init__(self, coordinator, reg: Reg) -> None:
        super().__init__(coordinator, reg.device, reg.key)
        self.reg = reg
        self._attr_name = reg.name
        self._attr_native_unit_of_measurement = reg.unit
        if reg.device_class:
            self._attr_device_class = SensorDeviceClass(reg.device_class)
        if reg.state_class:
            self._attr_state_class = SensorStateClass(reg.state_class)
        if reg.options is not None:
            self._attr_options = list(dict.fromkeys(reg.options.values()))
        if reg.precision is not None and reg.device_class != "enum":
            self._attr_suggested_display_precision = reg.precision
        if reg.display_precision is not None:
            self._attr_suggested_display_precision = reg.display_precision
        if reg.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = reg.enabled
        if reg.icon:
            self._attr_icon = reg.icon

    @property
    def native_value(self):
        value = decode(self.reg, self.coordinator.data)
        if self.reg.options is not None and value not in self._attr_options:
            return None  # unknown enum code; raw value is in diagnostics
        return value


class PvTotalSensor(SolaxEntity, SensorEntity):
    _attr_name = "Solar power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "W"
    _attr_icon = "mdi:solar-power"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, DEV_INVERTER, "pv_power")

    @property
    def native_value(self):
        pv = [r for r in SENSORS if r.key in ("pv1_power", "pv2_power")]
        values = [decode(r, self.coordinator.data) for r in pv]
        if any(v is None for v in values):
            return None
        return sum(values)
