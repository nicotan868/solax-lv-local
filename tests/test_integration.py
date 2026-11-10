"""Tests for the SolaX LV Local integration against a fake inverter."""

from __future__ import annotations


import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.solax_lv_local.client import ModbusExceptionResponse, RtuOverTcpClient
from custom_components.solax_lv_local.const import CONF_UNIT_ID, DOMAIN
from custom_components.solax_lv_local.registers import BLOCKS, CONTROLS, IDENTITY, SENSORS


def test_every_register_is_polled():
    covered = {(b.function, b.start + i) for b in BLOCKS for i in range(b.count)}
    for reg in SENSORS:
        for i in range(reg.size):
            assert (reg.function, reg.address + i) in covered, reg.key
    for c in CONTROLS:
        assert (3, c.address) in covered, c.key
    assert len({r.key for r in SENSORS}) == len(SENSORS)
    assert len({c.key for c in CONTROLS}) == len(CONTROLS)
    assert IDENTITY


async def test_client_read_write_and_exception(fake_inverter):
    client = RtuOverTcpClient("127.0.0.1", fake_inverter.port)
    assert await client.read_input(0x0100, 1) == [2274]
    await client.write_register(0x2598, 1600)
    assert await client.read_holding(0x2598, 1) == [1600]
    with pytest.raises(ModbusExceptionResponse):
        await client.read_input(0x7000, 1)
    # still usable after an exception response
    assert await client.read_input(0x0106, 1) == [5000]
    await client.close()


async def _setup(hass: HomeAssistant, port: int) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "127.0.0.1", CONF_PORT: port, CONF_UNIT_ID: 1},
        unique_id="HL1060TEST0001",
        title="SolaX HL1060TEST0001",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow(hass: HomeAssistant, fake_inverter):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: fake_inverter.port, CONF_UNIT_ID: 1}
    )
    assert result["type"] == "create_entry"
    assert result["result"].unique_id == "HL1060TEST0001"
    await hass.async_block_till_done()


async def test_config_flow_cannot_connect(hass: HomeAssistant, socket_enabled):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: 1, CONF_UNIT_ID: 1}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_states_devices_and_entities(hass: HomeAssistant, fake_inverter):
    entry = await _setup(hass, fake_inverter.port)
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    def state(unique_key: str):
        eid = ent_reg.async_get_entity_id(
            "sensor" if not unique_key.startswith(("number:", "time:")) else unique_key.split(":")[0],
            DOMAIN,
            f"HL1060TEST0001_{unique_key.split(':')[-1]}",
        )
        assert eid, unique_key
        return hass.states.get(eid)

    assert state("grid_voltage").state == "227.4"
    assert state("grid_power").state == "3109"
    assert state("pv1_power").state == "2392"
    assert state("pv2_power").state == "1786"
    assert state("pv_power").state == "4178"
    assert state("inverter_power").state == "4121"
    assert state("inverter_energy_total").state == "524.1"
    assert state("eps_power").state == "4111"
    assert state("battery_soc").state == "99.9"
    assert state("battery_power").state == "4"
    assert state("battery_temperature").state == "36.0"
    assert state("battery_charge_total").state == "77.8"
    assert state("cell_07_voltage").state == "3551"
    assert state("run_mode").state == "Run"
    assert state("ems_mode").state == "Force Time Use"
    assert state("battery_type").state == "SolaX LV"
    assert state("smart_load_port").state == "Generator"
    assert state("generator_rated_power").state == "3.5"
    assert state("time:discharge_1_start").state == "19:00:00"
    assert state("time:charge_1_end").state == "16:00:00"
    assert state("number:discharge_1_max_power").state == "1500"
    assert state("number:discharge_1_stop_soc").state == "10"

    devices = dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
    by_ident = {next(iter(d.identifiers))[1]: d for d in devices}
    inverter = by_ident["HL1060TEST0001_inverter"]
    assert inverter.name == "SolaX Local Inverter"
    assert inverter.serial_number == "HL1060TEST0001"
    assert inverter.sw_version == "LVESS_V436.01 B0"
    assert inverter.model == "X1-Hybrid-6-LV"
    battery = by_ident["HL1060TEST0001_battery"]
    assert battery.serial_number == "BATTEST0000001"
    assert battery.via_device_id == inverter.id
    assert len(devices) == 2
    pv1 = ent_reg.async_get(ent_reg.async_get_entity_id("sensor", DOMAIN, "HL1060TEST0001_pv1_power"))
    assert pv1.device_id == inverter.id
    assert ent_reg.async_get(ent_reg.async_get_entity_id("sensor", DOMAIN, "HL1060TEST0001_inverter_power_factor")).entity_category == "diagnostic"


async def test_number_write_guarded(hass: HomeAssistant, fake_inverter):
    await _setup(hass, fake_inverter.port)
    eid = er.async_get(hass).async_get_entity_id("number", DOMAIN, "HL1060TEST0001_discharge_1_max_power")
    # Same value: no write at all (saves EEPROM wear)
    await hass.services.async_call("number", "set_value", {"entity_id": eid, "value": 1500}, blocking=True)
    assert fake_inverter.writes == []
    # New value: written and read back
    await hass.services.async_call("number", "set_value", {"entity_id": eid, "value": 1800}, blocking=True)
    assert fake_inverter.writes == [(0x2598, 1800)]
    assert hass.states.get(eid).state == "1800"
    assert hass.states.get(eid).attributes["writes_left_today"] == 9
    # Out of range is refused before anything is sent
    with pytest.raises((ServiceValidationError, ValueError)):
        await hass.services.async_call("number", "set_value", {"entity_id": eid, "value": 9000}, blocking=True)
    assert len(fake_inverter.writes) == 1


async def test_daily_write_limit(hass: HomeAssistant, fake_inverter):
    entry = await _setup(hass, fake_inverter.port)
    coordinator = entry.runtime_data
    eid = er.async_get(hass).async_get_entity_id("number", DOMAIN, "HL1060TEST0001_charge_1_max_power")
    for value in range(100, 100 * (coordinator.daily_write_limit + 1), 100):
        await hass.services.async_call("number", "set_value", {"entity_id": eid, "value": value}, blocking=True)
    assert len(fake_inverter.writes) == coordinator.daily_write_limit
    with pytest.raises(HomeAssistantError, match="Daily write limit"):
        await hass.services.async_call("number", "set_value", {"entity_id": eid, "value": 4000}, blocking=True)
    assert len(fake_inverter.writes) == coordinator.daily_write_limit


async def test_time_write_and_rejection(hass: HomeAssistant, fake_inverter):
    await _setup(hass, fake_inverter.port)
    eid = er.async_get(hass).async_get_entity_id("time", DOMAIN, "HL1060TEST0001_discharge_1_start")
    await hass.services.async_call("time", "set_value", {"entity_id": eid, "time": "18:30:00"}, blocking=True)
    assert fake_inverter.writes == [(0x2582, (18 << 8) | 30)]
    assert hass.states.get(eid).state == "18:30:00"
    fake_inverter.reject_writes = True
    with pytest.raises(HomeAssistantError, match="failed"):
        await hass.services.async_call("time", "set_value", {"entity_id": eid, "time": "18:45:00"}, blocking=True)
    assert hass.states.get(eid).state == "18:30:00"


async def test_offline_then_recovers(hass: HomeAssistant, fake_inverter):
    entry = await _setup(hass, fake_inverter.port)
    coordinator = entry.runtime_data
    await fake_inverter.stop()
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    await fake_inverter.start()
    await coordinator.async_refresh()
    assert coordinator.last_update_success


async def test_diagnostics(hass: HomeAssistant, fake_inverter):
    from custom_components.solax_lv_local.diagnostics import async_get_config_entry_diagnostics

    entry = await _setup(hass, fake_inverter.port)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["identity"]["serial"] == "HL1060TEST0001"
    assert diag["registers"]["input:0x0550"] == 0
    assert diag["registers"]["input:0x0551"] == 3109


async def test_upgrade_from_separate_devices(hass: HomeAssistant, fake_inverter):
    """v0.1.0 entities on the old PV device keep their entity_id and move to the inverter."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "127.0.0.1", CONF_PORT: fake_inverter.port, CONF_UNIT_ID: 1},
        unique_id="HL1060TEST0001",
    )
    entry.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    old_dev = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "HL1060TEST0001_pv")}, name="SolaX Local PV"
    )
    old = ent_reg.async_get_or_create(
        "sensor", DOMAIN, "HL1060TEST0001_pv1_power", config_entry=entry, device_id=old_dev.id,
        suggested_object_id="solax_local_pv1_power",
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    moved = ent_reg.async_get(old.entity_id)
    assert moved is not None and moved.entity_id == "sensor.solax_local_pv1_power"
    inverter = next(
        d for d in dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
        if (DOMAIN, "HL1060TEST0001_inverter") in d.identifiers
    )
    assert moved.device_id == inverter.id
    assert dev_reg.async_get(old_dev.id) is None
    assert hass.states.get("sensor.solax_local_pv1_power").state == "2392"
