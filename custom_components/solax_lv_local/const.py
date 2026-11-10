"""Constants for the SolaX LV Local integration."""

from __future__ import annotations

DOMAIN = "solax_lv_local"
MANUFACTURER = "SolaX Power"

CONF_UNIT_ID = "unit_id"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_DAILY_WRITE_LIMIT = "daily_write_limit"

DEFAULT_PORT = 4001
DEFAULT_UNIT_ID = 1
DEFAULT_SCAN_INTERVAL = 10  # seconds, fast group
DEFAULT_DAILY_WRITE_LIMIT = 10  # writes per setting per day (EEPROM wear guard)

# Poll groups: fast every cycle, medium every Nth cycle, slow every Mth cycle.
MEDIUM_EVERY = 6  # 60 s at the default 10 s
SLOW_EVERY = 30  # 5 min at the default 10 s

# Device keys
DEV_INVERTER = "inverter"
DEV_BATTERY = "battery"
DEV_PV = "pv"
DEV_EPS = "eps"
DEV_GENERATOR = "generator"

DEVICE_NAMES = {
    DEV_INVERTER: "SolaX Local Inverter",
    DEV_BATTERY: "SolaX Local Battery",
    DEV_PV: "SolaX Local PV",
    DEV_EPS: "SolaX Local EPS",
    DEV_GENERATOR: "SolaX Local Generator",
}
