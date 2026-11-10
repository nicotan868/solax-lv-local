"""Diagnostics: raw register dump and write log."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import SolaxConfigEntry


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: SolaxConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "identity": coordinator.identity,
        "options": dict(entry.options),
        "registers": {
            f"{'input' if fc == 4 else 'holding'}:{addr:#06x}": value
            for (fc, addr), value in sorted(coordinator.data.items())
        },
        "write_log": coordinator.write_log,
    }
