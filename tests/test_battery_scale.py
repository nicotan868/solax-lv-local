"""Regression coverage for battery power's watt-per-count scale."""
import pytest

from custom_components.solax_lv_local.registers import SENSORS, decode


@pytest.mark.parametrize("watts", [1500, -1500, 1610, -1510, 10, -10, 99, -99, 0, 4, -4, 9, -9])
def test_battery_register_is_watts_with_ten_watt_deadband(watts):
    reg = next(r for r in SENSORS if r.key == "battery_power")
    raw = watts & 0xFFFFFFFF
    cache = {(reg.function, reg.address): raw >> 16,
             (reg.function, reg.address + 1): raw & 0xFFFF}
    expected = 0 if abs(watts) < 10 else watts
    assert decode(reg, cache) == expected
