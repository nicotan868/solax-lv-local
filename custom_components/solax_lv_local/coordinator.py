"""Data coordinator: polls register blocks and performs guarded writes."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import FC_READ_HOLDING, ModbusError, RtuOverTcpClient
from .const import (
    CONF_DAILY_WRITE_LIMIT,
    CONF_SCAN_INTERVAL,
    DEFAULT_DAILY_WRITE_LIMIT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MEDIUM_EVERY,
    SLOW_EVERY,
)
from .registers import BLOCKS, FAST, IDENTITY, MEDIUM, SLOW, Control

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
WRITE_LOG_SIZE = 50


def _text(regs: list[int]) -> str:
    raw = b"".join(r.to_bytes(2, "big") for r in regs)
    return raw.split(b"\x00", 1)[0].decode("ascii", "replace").strip()


class SolaxCoordinator(DataUpdateCoordinator[dict[tuple[int, int], int]]):
    """Holds a cache of raw register values keyed by (function, address)."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: RtuOverTcpClient) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self.identity: dict[str, Any] = {}
        self.inverter_device_id: str | None = None
        self._cycle = 0
        self._cache: dict[tuple[int, int], int] = {}
        self._store: Store[dict[str, Any]] = Store(hass, STORE_VERSION, f"{DOMAIN}.{entry.entry_id}.writes")
        self._writes: dict[str, Any] = {"day": None, "counts": {}, "log": []}

    @property
    def daily_write_limit(self) -> int:
        return int(self.config_entry.options.get(CONF_DAILY_WRITE_LIMIT, DEFAULT_DAILY_WRITE_LIMIT))

    async def async_load_identity(self) -> None:
        """Read model/serial/firmware once at setup."""
        ident: dict[str, Any] = {}
        for key, (function, address, count) in IDENTITY.items():
            try:
                regs = await self.client.read_registers(function, address, count)
            except ModbusError as err:
                _LOGGER.debug("Identity read %s failed: %s", key, err)
                continue
            ident[key] = regs[0] / 10 if key == "rated_power" else _text(regs)
        self.identity = ident
        stored = await self._store.async_load()
        if stored:
            self._writes = stored

    async def _async_update_data(self) -> dict[tuple[int, int], int]:
        groups = {FAST}
        if self._cycle % MEDIUM_EVERY == 0:
            groups.add(MEDIUM)
        if self._cycle % SLOW_EVERY == 0:
            groups.add(SLOW)
        self._cycle += 1
        errors = 0
        for block in BLOCKS:
            if block.group not in groups:
                continue
            try:
                regs = await self.client.read_registers(block.function, block.start, block.count)
            except ModbusError as err:
                errors += 1
                _LOGGER.debug("Block %#06x failed: %s", block.start, err)
                if block.group == FAST and not self.client.connected:
                    raise UpdateFailed(f"Inverter not reachable: {err}") from err
                continue
            for i, value in enumerate(regs):
                self._cache[(block.function, block.start + i)] = value
        if errors and not self._cache:
            raise UpdateFailed("No data read from inverter")
        return dict(self._cache)

    # ---------------------------------------------------------------- writes
    def _roll_day(self) -> None:
        today = dt_util.now().date().isoformat()
        if self._writes.get("day") != today:
            self._writes["day"] = today
            self._writes["counts"] = {}

    def writes_left(self, key: str) -> int:
        self._roll_day()
        return max(0, self.daily_write_limit - self._writes["counts"].get(key, 0))

    @property
    def write_log(self) -> list[dict[str, Any]]:
        return list(self._writes.get("log", []))

    async def async_write(self, control: Control, value: int, label: str) -> None:
        """Write one EEPROM-backed setting with range/limit checks and read-back."""
        current = self._cache.get((FC_READ_HOLDING, control.address))
        if current == value:
            _LOGGER.info("%s already %s; not writing (saves EEPROM wear)", control.name, label)
            return
        self._roll_day()
        if self.writes_left(control.key) <= 0:
            raise HomeAssistantError(
                f"Daily write limit ({self.daily_write_limit}) reached for '{control.name}'. "
                "These settings are stored in the inverter's EEPROM, which wears out with frequent "
                "writes. Try again tomorrow or raise the limit in the integration options."
            )
        try:
            await self.client.write_register(control.address, value)
            readback = (await self.client.read_holding(control.address, 1))[0]
        except ModbusError as err:
            raise HomeAssistantError(f"Writing '{control.name}' failed: {err}") from err
        self._writes["counts"][control.key] = self._writes["counts"].get(control.key, 0) + 1
        self._writes["log"] = (
            self._writes.get("log", [])
            + [
                {
                    "time": dt_util.now().isoformat(timespec="seconds"),
                    "setting": control.name,
                    "register": f"{control.address:#06x}",
                    "old": current,
                    "new": value,
                    "label": label,
                    "readback": readback,
                }
            ]
        )[-WRITE_LOG_SIZE:]
        await self._store.async_save(self._writes)
        self._cache[(FC_READ_HOLDING, control.address)] = readback
        _LOGGER.warning(
            "SolaX setting changed: %s = %s (register %#06x, %s -> %s)",
            control.name, label, control.address, current, readback,
        )
        self.async_set_updated_data(dict(self._cache))
        if readback != value:
            raise HomeAssistantError(
                f"Inverter did not accept '{control.name}' (read back {readback}, expected {value})."
            )
