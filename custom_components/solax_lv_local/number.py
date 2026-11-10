"""Number controls (EEPROM-backed inverter settings)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SolaxConfigEntry
from .client import FC_READ_HOLDING
from .const import DEV_INVERTER
from .entity import SolaxEntity
from .registers import CONTROLS, Control


async def async_setup_entry(
    hass: HomeAssistant, entry: SolaxConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(SolaxNumber(coordinator, c) for c in CONTROLS if c.kind == "number")


class SolaxNumber(SolaxEntity, NumberEntity):
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, control: Control) -> None:
        super().__init__(coordinator, DEV_INVERTER, control.key)
        self.control = control
        self._attr_name = control.name
        self._attr_native_min_value = control.minimum
        self._attr_native_max_value = control.maximum
        self._attr_native_step = control.step
        self._attr_native_unit_of_measurement = control.unit
        self._attr_icon = control.icon

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get((FC_READ_HOLDING, self.control.address))

    @property
    def extra_state_attributes(self):
        return {"writes_left_today": self.coordinator.writes_left(self.control.key)}

    async def async_set_native_value(self, value: float) -> None:
        c = self.control
        if not c.minimum <= value <= c.maximum:
            raise ValueError(f"{c.name} must be between {c.minimum} and {c.maximum}")
        raw = int(round(value))
        await self.coordinator.async_write(c, raw, f"{raw}{c.unit or ''}")
