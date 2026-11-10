"""Time controls for the charge/discharge windows."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SolaxConfigEntry
from .client import FC_READ_HOLDING
from .const import DEV_INVERTER
from .entity import SolaxEntity
from .registers import CONTROLS, Control, decode_time, encode_time


async def async_setup_entry(
    hass: HomeAssistant, entry: SolaxConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(SolaxTime(coordinator, c) for c in CONTROLS if c.kind == "time")


class SolaxTime(SolaxEntity, TimeEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, control: Control) -> None:
        super().__init__(coordinator, DEV_INVERTER, control.key)
        self.control = control
        self._attr_name = control.name
        self._attr_icon = control.icon

    @property
    def native_value(self) -> time | None:
        raw = self.coordinator.data.get((FC_READ_HOLDING, self.control.address))
        if raw is None:
            return None
        hm = decode_time(raw)
        return time(*hm) if hm else None

    @property
    def extra_state_attributes(self):
        return {"writes_left_today": self.coordinator.writes_left(self.control.key)}

    async def async_set_value(self, value: time) -> None:
        raw = encode_time(value.hour, value.minute)
        await self.coordinator.async_write(self.control, raw, value.strftime("%H:%M"))
