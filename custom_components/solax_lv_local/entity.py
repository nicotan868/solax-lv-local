"""Shared entity base and device info."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEV_BATTERY, DEV_INVERTER, DEVICE_NAMES, DOMAIN, MANUFACTURER
from .coordinator import SolaxCoordinator

MODELS = {
    DEV_INVERTER: "X1-Hybrid-LV",
    DEV_BATTERY: "LV battery (BMS)",
}


def device_info(coordinator: SolaxCoordinator, device: str) -> DeviceInfo:
    ident = coordinator.identity
    serial = ident.get("serial", coordinator.config_entry.entry_id)
    info = DeviceInfo(
        identifiers={(DOMAIN, f"{serial}_{device}")},
        name=DEVICE_NAMES[device],
        manufacturer=MANUFACTURER,
        model=MODELS[device],
    )
    if device == DEV_INVERTER:
        rated = ident.get("rated_power")
        if rated:
            info["model"] = f"X1-Hybrid-{rated:g}-LV"
        info["serial_number"] = serial
        if ident.get("firmware"):
            info["sw_version"] = ident["firmware"]
        info["configuration_url"] = f"http://{coordinator.client.host}"
    else:
        if coordinator.inverter_device_id:
            info["via_device_id"] = coordinator.inverter_device_id
        if device == DEV_BATTERY and ident.get("battery_serial"):
            info["serial_number"] = ident["battery_serial"]
    return info


class SolaxEntity(CoordinatorEntity[SolaxCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SolaxCoordinator, device: str, key: str) -> None:
        super().__init__(coordinator)
        serial = coordinator.identity.get("serial", coordinator.config_entry.entry_id)
        self._attr_unique_id = f"{serial}_{key}"
        self._attr_device_info = device_info(coordinator, device)
