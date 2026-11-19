"""Sensors for the SolaX LV Local integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SolaxConfigEntry
from .const import DEV_BATTERY_2, DEV_INVERTER
from .entity import SolaxEntity
from .registers import PACK2_SENSORS, SENSORS, Reg, decode, pack2_cells


async def async_setup_entry(
    hass: HomeAssistant, entry: SolaxConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [SolaxSensor(coordinator, reg) for reg in SENSORS]
    entities.append(PvTotalSensor(coordinator))
    # Second battery pack: only when the inverter actually reports its cells.
    if pack2_cells(coordinator.data) is not None:
        entities.extend(SolaxSensor(coordinator, reg) for reg in PACK2_SENSORS)
        entities.extend(Pack2CellStat(coordinator, *stat) for stat in PACK2_STATS)
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


# key, name, unit, device class, function of the 16 cell voltages (mV)
PACK2_STATS = (
    ("pack2_voltage", "Voltage", "V", SensorDeviceClass.VOLTAGE, lambda c: round(sum(c) / 1000, 2)),
    ("pack2_cell_voltage_max", "Cell voltage max", "mV", SensorDeviceClass.VOLTAGE, max),
    ("pack2_cell_voltage_min", "Cell voltage min", "mV", SensorDeviceClass.VOLTAGE, min),
    ("pack2_cell_voltage_spread", "Cell voltage spread", "mV", SensorDeviceClass.VOLTAGE, lambda c: max(c) - min(c)),
)


class Pack2CellStat(SolaxEntity, SensorEntity):
    """Derived from pack 2's cell voltages (sum, max, min, max-min balance)."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, key, name, unit, device_class, func) -> None:
        super().__init__(coordinator, DEV_BATTERY_2, key)
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._func = func
        if unit == "V":
            self._attr_suggested_display_precision = 2

    @property
    def native_value(self):
        cells = pack2_cells(self.coordinator.data)
        return None if cells is None else self._func(cells)
