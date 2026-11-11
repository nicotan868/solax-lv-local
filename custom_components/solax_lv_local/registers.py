"""Register map for the SolaX X1-Hybrid-LV (serial prefix HL1060).

Sources: SolaX "X1-Hybrid-Lv Modbus RTU V1.00" and the more detailed
"X1-Lite-Lv Modbus RTU Detailed V1.00" (same register layout). Every address
below was checked live against an HL1060 unit (firmware LVESS_V436.01) and the
SolaX cloud. 32-bit values are big-endian word order (high word first), even
though the Lite-LV sheet header says little endian.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .client import FC_READ_HOLDING, FC_READ_INPUT
from .const import DEV_BATTERY, DEV_INVERTER

FAST, MEDIUM, SLOW = "fast", "medium", "slow"


@dataclass(frozen=True)
class Block:
    """A contiguous register range read in one request."""

    function: int
    start: int
    count: int
    group: str


# Contiguous ranges, each verified readable without exceptions.
BLOCKS: tuple[Block, ...] = (
    Block(FC_READ_INPUT, 0x0100, 0x07, FAST),  # grid V / Hz
    Block(FC_READ_INPUT, 0x0180, 0x10, FAST),  # inverter A, W, VA, energy, PF
    Block(FC_READ_INPUT, 0x028B, 0x0B, FAST),  # PV1/PV2
    Block(FC_READ_INPUT, 0x0400, 0x05, FAST),  # EPS
    Block(FC_READ_INPUT, 0x0440, 0x05, FAST),  # generator
    Block(FC_READ_INPUT, 0x0480, 0x0E, FAST),  # battery
    Block(FC_READ_INPUT, 0x0550, 0x02, FAST),  # grid power
    Block(FC_READ_INPUT, 0x0C00, 0x0C, FAST),  # BMS summary incl. SoC
    Block(FC_READ_INPUT, 0x0200, 0x19, MEDIUM),  # run mode, temps, faults
    Block(FC_READ_INPUT, 0x0600, 0x01, MEDIUM),  # DC bus
    Block(FC_READ_INPUT, 0x0C2C, 0x01, SLOW),  # cycles
    Block(FC_READ_INPUT, 0x0C97, 0x06, SLOW),  # BMS temperatures
    Block(FC_READ_INPUT, 0x0CD7, 0x10, SLOW),  # 16 cell voltages
    Block(FC_READ_HOLDING, 0x2302, 0x02, SLOW),  # export / power limit
    Block(FC_READ_HOLDING, 0x2500, 0x1C, SLOW),  # battery & EMS settings
    Block(FC_READ_HOLDING, 0x2542, 0x01, SLOW),  # generator rated power
    Block(FC_READ_HOLDING, 0x2580, 0x1B, SLOW),  # time-of-use periods
)

# Identity registers read once at setup.
IDENTITY = {
    "producer": (FC_READ_INPUT, 0x0002, 8),
    "firmware": (FC_READ_INPUT, 0x0022, 8),
    "serial": (FC_READ_INPUT, 0x0032, 8),
    "rated_power": (FC_READ_INPUT, 0x0043, 1),
    "battery_serial": (FC_READ_INPUT, 0x0DD7, 7),
}


@dataclass(frozen=True)
class Reg:
    """One value decoded from the register cache."""

    key: str
    name: str
    device: str
    function: int
    address: int
    dtype: str = "u16"  # u16, s16, u32, s32
    scale: float = 1
    precision: int | None = None
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = "measurement"
    diagnostic: bool = False
    enabled: bool = True
    options: dict[int, str] | None = None  # enum mapping
    display_precision: int | None = None  # UI rounding (value keeps full precision)
    deadband: float | None = None  # |value| below this reads as 0 (idle noise)
    icon: str | None = None

    @property
    def size(self) -> int:
        return 2 if self.dtype in ("u32", "s32") else 1


def decode(reg: Reg, cache: dict[tuple[int, int], int]):
    """Return the scaled value, or None if registers are missing."""
    try:
        hi = cache[(reg.function, reg.address)]
        if reg.size == 2:
            raw = (hi << 16) | cache[(reg.function, reg.address + 1)]
            if reg.dtype == "s32" and raw >= 1 << 31:
                raw -= 1 << 32
        else:
            raw = hi
            if reg.dtype == "s16" and raw >= 1 << 15:
                raw -= 1 << 16
    except KeyError:
        return None
    if reg.options is not None:
        return reg.options.get(raw, f"unknown ({raw})")
    value = raw * reg.scale
    if reg.deadband is not None and abs(value) < reg.deadband:
        value = 0
    if reg.precision is not None:
        return round(value, reg.precision) if reg.precision else int(round(value))
    return value


I, H = FC_READ_INPUT, FC_READ_HOLDING
V, A, W, VA, HZ, C, KWH, PCT, MV = "V", "A", "W", "VA", "Hz", "°C", "kWh", "%", "mV"

RUN_MODE = {0: "Init", 1: "Idle", 2: "Start", 3: "Run", 4: "Stop", 5: "Upgrade"}
EMS_MODE = {0: "Backup", 1: "Self Use", 2: "MKS", 3: "Force Time Use"}
CHARGE_SOURCE = {0: "PV Only", 2: "PV Then Utility", 3: "PV And Utility"}
SMART_LOAD = {0: "None", 1: "Smart Load", 2: "Generator"}
BATTERY_TYPE = {
    0x82: "Soluna", 0xAA: "AGM", 0xAB: "FLD", 0xAC: "TBL", 0xEA: "SolaX LV",
    0xEB: "Volta", 0xEC: "Lemon", 0xED: "Pylontech",
}

SENSORS: tuple[Reg, ...] = (
    # ---- Inverter / grid
    Reg("grid_voltage", "Grid – 2 Voltage", DEV_INVERTER, I, 0x0100, scale=0.1, precision=1, unit=V, device_class="voltage"),
    Reg("ac_voltage", "Output – 3 Voltage", DEV_INVERTER, I, 0x0103, scale=0.1, precision=1, unit=V, device_class="voltage"),
    Reg("grid_frequency", "Grid – 3 Frequency", DEV_INVERTER, I, 0x0106, scale=0.01, precision=2, unit=HZ, device_class="frequency"),
    Reg("grid_power", "Grid – 1 Power", DEV_INVERTER, I, 0x0550, "s32", unit=W, device_class="power", icon="mdi:transmission-tower"),
    Reg("inverter_current", "Output – 2 Current", DEV_INVERTER, I, 0x0180, "s16", 0.1, 1, A, "current"),
    Reg("inverter_power", "Output – 1 Power", DEV_INVERTER, I, 0x0183, "s32", unit=W, device_class="power"),
    Reg("inverter_apparent_power", "Apparent power", DEV_INVERTER, I, 0x0187, "u32", unit=VA, device_class="apparent_power", diagnostic=True),
    Reg("inverter_power_factor", "Power factor", DEV_INVERTER, I, 0x018F, "s16", 0.001, 3, device_class="power_factor", diagnostic=True),
    Reg("inverter_energy_today", "Output – 4 Energy today", DEV_INVERTER, I, 0x0189, "u16", 0.1, 1, KWH, "energy", "total_increasing"),
    Reg("inverter_energy_total", "Output – 5 Energy total", DEV_INVERTER, I, 0x018A, "u32", 0.1, 1, KWH, "energy", "total_increasing"),
    Reg("run_mode", "Run mode", DEV_INVERTER, I, 0x0200, options=RUN_MODE, state_class=None, device_class="enum"),
    Reg("inverter_temperature", "Temperature", DEV_INVERTER, I, 0x0202, "s16", 0.1, 1, C, "temperature"),
    Reg("busbar_positive_temperature", "Battery busbar + temperature", DEV_INVERTER, I, 0x020E, "s16", 0.1, 1, C, "temperature", diagnostic=True),
    Reg("busbar_negative_temperature", "Battery busbar - temperature", DEV_INVERTER, I, 0x020F, "s16", 0.1, 1, C, "temperature", diagnostic=True),
    Reg("insulation_resistance", "Insulation resistance", DEV_INVERTER, I, 0x0210, scale=0.1, precision=1, unit="kΩ", diagnostic=True, icon="mdi:omega"),
    Reg("fault_code", "Fault code", DEV_INVERTER, I, 0x0217, state_class=None, diagnostic=True, icon="mdi:alert-circle-outline"),
    Reg("warning_code", "Warning code", DEV_INVERTER, I, 0x0218, state_class=None, diagnostic=True, icon="mdi:alert-outline"),
    Reg("dc_bus_voltage", "DC bus voltage", DEV_INVERTER, I, 0x0600, "s16", 0.1, 1, V, "voltage", diagnostic=True),
    # ---- Inverter settings (read-only views; writable ones are number/time entities)
    Reg("export_limit", "Export limit", DEV_INVERTER, H, 0x2302, unit=PCT, state_class=None, diagnostic=True, icon="mdi:transmission-tower-export"),
    Reg("power_limit", "Power limit", DEV_INVERTER, H, 0x2303, unit=PCT, state_class=None, diagnostic=True),
    Reg("ems_mode", "Work mode", DEV_INVERTER, H, 0x250B, options=EMS_MODE, state_class=None, device_class="enum", diagnostic=True, icon="mdi:cog"),
    Reg("charge_source", "Charge source", DEV_INVERTER, H, 0x251A, options=CHARGE_SOURCE, state_class=None, device_class="enum", diagnostic=True),
    Reg("smart_load_port", "Smart load port", DEV_INVERTER, H, 0x251B, options=SMART_LOAD, state_class=None, device_class="enum", diagnostic=True),
    Reg("eps_min_soc", "EPS min SoC", DEV_INVERTER, H, 0x2515, unit=PCT, state_class=None, diagnostic=True),
    Reg("recover_soc", "Recover SoC", DEV_INVERTER, H, 0x2516, unit=PCT, state_class=None, diagnostic=True),
    Reg("max_grid_charge_current", "Max grid charge current", DEV_INVERTER, H, 0x2517, unit=A, state_class=None, diagnostic=True),
    Reg("generator_rated_power", "Generator rated power", DEV_INVERTER, H, 0x2542, scale=0.01, precision=2, unit="kW", state_class=None, diagnostic=True),
    # ---- PV
    Reg("pv1_voltage", "Solar string 1 – 3 Voltage", DEV_INVERTER, I, 0x028B, "s16", 0.1, 1, V, "voltage"),
    Reg("pv1_current", "Solar string 1 – 2 Current", DEV_INVERTER, I, 0x028C, "s16", 0.1, 1, A, "current"),
    Reg("pv1_power", "Solar string 1 – 1 Power", DEV_INVERTER, I, 0x028D, "u32", unit=W, device_class="power"),
    Reg("pv2_voltage", "Solar string 2 – 3 Voltage", DEV_INVERTER, I, 0x0292, "s16", 0.1, 1, V, "voltage"),
    Reg("pv2_current", "Solar string 2 – 2 Current", DEV_INVERTER, I, 0x0293, "s16", 0.1, 1, A, "current"),
    Reg("pv2_power", "Solar string 2 – 1 Power", DEV_INVERTER, I, 0x0294, "u32", unit=W, device_class="power"),
    # ---- EPS (backup output)
    Reg("eps_voltage", "Backup (EPS) – 3 Voltage", DEV_INVERTER, I, 0x0400, "s16", 0.1, 1, V, "voltage"),
    Reg("eps_current", "Backup (EPS) – 2 Current", DEV_INVERTER, I, 0x0401, "s16", 0.1, 1, A, "current"),
    Reg("eps_power", "Backup (EPS) – 1 Power", DEV_INVERTER, I, 0x0402, "s32", 0.1, 0, W, "power"),
    Reg("eps_frequency", "Backup (EPS) – 4 Frequency", DEV_INVERTER, I, 0x0404, scale=0.01, precision=2, unit=HZ, device_class="frequency"),
    # ---- Generator / V2L input
    Reg("generator_voltage", "Generator – 3 Voltage", DEV_INVERTER, I, 0x0440, "s16", 0.1, 1, V, "voltage"),
    Reg("generator_current", "Generator – 2 Current", DEV_INVERTER, I, 0x0441, "s16", 0.1, 1, A, "current"),
    Reg("generator_power", "Generator – 1 Power", DEV_INVERTER, I, 0x0442, "s32", 0.1, 0, W, "power"),
    # Scale per the SolaX sheet (0.1 Hz); unverified until a generator/V2L is connected.
    Reg("generator_frequency", "Generator – 4 Frequency", DEV_INVERTER, I, 0x0444, scale=0.1, precision=1, unit=HZ, device_class="frequency"),
    # ---- Battery
    Reg("battery_soc", "State of charge", DEV_BATTERY, I, 0x0C04, scale=0.1, precision=1, unit=PCT, device_class="battery", display_precision=0),
    Reg("battery_voltage", "Voltage", DEV_BATTERY, I, 0x0480, "s16", 0.1, 1, V, "voltage"),
    Reg("battery_current", "Current", DEV_BATTERY, I, 0x0481, "s16", 0.1, 1, A, "current"),
    # 1 W/count, validated against battery V × A and cloud in both directions.
    # Unlike EPS/generator power, this register must NOT be scaled by 0.1.
    Reg("battery_power", "Power", DEV_BATTERY, I, 0x0482, "s32", 1, 0, W, "power", deadband=10),
    Reg("battery_temperature", "Temperature", DEV_BATTERY, I, 0x0484, "s16", 0.1, 1, C, "temperature"),
    Reg("battery_charge_today", "Charged today", DEV_BATTERY, I, 0x0488, "u16", 0.1, 1, KWH, "energy", "total_increasing"),
    Reg("battery_charge_total", "Charged total", DEV_BATTERY, I, 0x0489, "u32", 0.1, 1, KWH, "energy", "total_increasing"),
    Reg("battery_discharge_today", "Discharged today", DEV_BATTERY, I, 0x048B, "u16", 0.1, 1, KWH, "energy", "total_increasing"),
    Reg("battery_discharge_total", "Discharged total", DEV_BATTERY, I, 0x048C, "u32", 0.1, 1, KWH, "energy", "total_increasing"),
    Reg("bms_state", "BMS state", DEV_BATTERY, I, 0x0C00, state_class=None, diagnostic=True),
    Reg("cell_voltage_max", "Cell voltage max", DEV_BATTERY, I, 0x0C05, unit=MV, device_class="voltage"),
    Reg("cell_voltage_min", "Cell voltage min", DEV_BATTERY, I, 0x0C06, unit=MV, device_class="voltage"),
    Reg("cell_temperature_max", "Cell temperature max", DEV_BATTERY, I, 0x0C07, "s16", unit=C, device_class="temperature"),
    Reg("cell_temperature_min", "Cell temperature min", DEV_BATTERY, I, 0x0C08, "s16", unit=C, device_class="temperature"),
    Reg("bms_charge_current_limit", "BMS charge current limit", DEV_BATTERY, I, 0x0C09, unit=A, device_class="current", diagnostic=True),
    Reg("bms_discharge_current_limit", "BMS discharge current limit", DEV_BATTERY, I, 0x0C0A, unit=A, device_class="current", diagnostic=True),
    Reg("bms_fault_level", "BMS fault level", DEV_BATTERY, I, 0x0C0B, state_class=None, diagnostic=True),
    Reg("battery_cycles", "Cycles", DEV_BATTERY, I, 0x0C2C, state_class="total_increasing", icon="mdi:battery-sync"),
    Reg("battery_type", "Battery type", DEV_BATTERY, H, 0x2500, options=BATTERY_TYPE, state_class=None, device_class="enum", diagnostic=True),
    Reg("max_charge_current", "Max charge current", DEV_BATTERY, H, 0x2504, unit=A, state_class=None, diagnostic=True),
    Reg("max_discharge_current", "Max discharge current", DEV_BATTERY, H, 0x2505, unit=A, state_class=None, diagnostic=True),
    Reg("max_charge_voltage", "Max charge voltage", DEV_BATTERY, H, 0x2506, scale=0.1, precision=1, unit=V, state_class=None, diagnostic=True),
    Reg("float_voltage", "Float voltage", DEV_BATTERY, H, 0x2507, scale=0.1, precision=1, unit=V, state_class=None, diagnostic=True),
    Reg("min_discharge_voltage", "Min discharge voltage", DEV_BATTERY, H, 0x2508, scale=0.1, precision=1, unit=V, state_class=None, diagnostic=True),
    *(
        Reg(f"cell_{i + 1:02d}_voltage", f"Cell {i + 1:02d} voltage", DEV_BATTERY, I, 0x0CD7 + i,
            unit=MV, device_class="voltage", diagnostic=True)
        for i in range(16)
    ),
    *(
        Reg(f"bms_temperature_{i + 1}", f"BMS temperature {i + 1}", DEV_BATTERY, I, 0x0C97 + i, "s16",
            unit=C, device_class="temperature", diagnostic=True)
        for i in range(6)
    ),
)


@dataclass(frozen=True)
class Control:
    """A writable holding register (all are EEPROM-backed on this inverter)."""

    key: str
    name: str
    address: int
    kind: str  # "number" or "time"
    minimum: float = 0
    maximum: float = 0
    step: float = 1
    unit: str | None = None
    icon: str | None = None
    extra: dict = field(default_factory=dict)


CONTROLS: tuple[Control, ...] = (
    *(
        c
        for p, (cs, ce, ds, de) in enumerate(
            ((0x2580, 0x2581, 0x2582, 0x2583), (0x2584, 0x2585, 0x2586, 0x2587), (0x2588, 0x2589, 0x258A, 0x258B)),
            start=1,
        )
        for c in (
            Control(f"charge_{p}_start", f"Charge {p} – 1 Start", cs, "time", icon="mdi:battery-clock"),
            Control(f"charge_{p}_end", f"Charge {p} – 2 End", ce, "time", icon="mdi:battery-clock"),
            Control(f"discharge_{p}_start", f"Discharge {p} – 1 Start", ds, "time", icon="mdi:battery-clock-outline"),
            Control(f"discharge_{p}_end", f"Discharge {p} – 2 End", de, "time", icon="mdi:battery-clock-outline"),
        )
    ),
    *(
        Control(f"discharge_{p}_stop_soc", f"Discharge {p} – 3 Stop SoC", 0x258F + p - 1, "number", 10, 40, 1, PCT, "mdi:battery-arrow-down")
        for p in (1, 2, 3)
    ),
    *(
        # Sheet says 20-99; the inverter ships with 100, so allow 100.
        Control(f"charge_{p}_stop_soc", f"Charge {p} – 3 Stop SoC", 0x2592 + p - 1, "number", 20, 100, 1, PCT, "mdi:battery-arrow-up")
        for p in (1, 2, 3)
    ),
    *(
        # Sheet allows up to 12000 W; capped at the 6 kW inverter rating.
        Control(f"charge_{p}_max_power", f"Charge {p} – 4 Max power", 0x2595 + p - 1, "number", 0, 6000, 100, W, "mdi:battery-charging")
        for p in (1, 2, 3)
    ),
    *(
        Control(f"discharge_{p}_max_power", f"Discharge {p} – 4 Max power", 0x2598 + p - 1, "number", 0, 6000, 100, W, "mdi:home-battery")
        for p in (1, 2, 3)
    ),
)


def encode_time(hour: int, minute: int) -> int:
    """High byte = hour, low byte = minute."""
    return (hour << 8) | minute


def decode_time(raw: int) -> tuple[int, int] | None:
    hour, minute = raw >> 8, raw & 0xFF
    if hour > 23 or minute > 59:
        return None
    return hour, minute
