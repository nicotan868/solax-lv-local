"""SolaX X1-Hybrid-LV local Modbus (RTU over TCP) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .client import RtuOverTcpClient
from .const import CONF_UNIT_ID, DEFAULT_UNIT_ID, DEV_INVERTER
from .coordinator import SolaxCoordinator
from .entity import device_info

PLATFORMS = [Platform.SENSOR, Platform.NUMBER, Platform.TIME]

type SolaxConfigEntry = ConfigEntry[SolaxCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SolaxConfigEntry) -> bool:
    client = RtuOverTcpClient(
        entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data.get(CONF_UNIT_ID, DEFAULT_UNIT_ID)
    )
    coordinator = SolaxCoordinator(hass, entry, client)
    await coordinator.async_load_identity()
    if not coordinator.identity.get("serial"):
        await client.close()
        raise ConfigEntryNotReady(f"No answer from inverter at {client.host}:{client.port}")
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    # Register the inverter first so the other devices can link to it.
    inverter = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **device_info(coordinator, DEV_INVERTER)
    )
    coordinator.inverter_device_id = inverter.id
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: SolaxConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SolaxConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.client.close()
    return ok
