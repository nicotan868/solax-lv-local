"""Config flow for SolaX LV Local."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback

from .client import FC_READ_INPUT, ModbusError, RtuOverTcpClient
from .const import (
    CONF_DAILY_WRITE_LIMIT,
    CONF_SCAN_INTERVAL,
    CONF_UNIT_ID,
    DEFAULT_DAILY_WRITE_LIMIT,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DOMAIN,
)

SUPPORTED_PREFIXES = ("HL1060",)


async def _probe(host: str, port: int, unit_id: int) -> str:
    client = RtuOverTcpClient(host, port, unit_id, timeout=3)
    try:
        regs = await client.read_registers(FC_READ_INPUT, 0x0032, 7)
    finally:
        await client.close()
    raw = b"".join(r.to_bytes(2, "big") for r in regs)
    return raw.split(b"\x00", 1)[0].decode("ascii", "replace").strip()


class SolaxLvConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._serial = ""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                serial = await _probe(user_input[CONF_HOST], user_input[CONF_PORT], user_input[CONF_UNIT_ID])
            except (ModbusError, OSError, TimeoutError):
                errors["base"] = "cannot_connect"
            else:
                if not serial:
                    errors["base"] = "no_serial"
                else:
                    await self.async_set_unique_id(serial)
                    self._abort_if_unique_id_configured(updates=user_input)
                    self._data, self._serial = user_input, serial
                    if not serial.startswith(SUPPORTED_PREFIXES):
                        return await self.async_step_unsupported()
                    return self.async_create_entry(title=f"SolaX {serial}", data=user_input)
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=(user_input or {}).get(CONF_HOST, "")): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(int, vol.Range(1, 65535)),
                vol.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): vol.All(int, vol.Range(1, 247)),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_unsupported(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Warn when the serial prefix was not verified against this register map."""
        if user_input is not None:
            return self.async_create_entry(title=f"SolaX {self._serial}", data=self._data)
        return self.async_show_form(
            step_id="unsupported",
            data_schema=vol.Schema({}),
            description_placeholders={"serial": self._serial},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SolaxLvOptionsFlow()


class SolaxLvOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL, default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ): vol.All(int, vol.Range(1, 300)),
                vol.Required(
                    CONF_DAILY_WRITE_LIMIT, default=opts.get(CONF_DAILY_WRITE_LIMIT, DEFAULT_DAILY_WRITE_LIMIT)
                ): vol.All(int, vol.Range(1, 50)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
