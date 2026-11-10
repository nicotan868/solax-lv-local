# SolaX LV Local

Home Assistant integration for the **SolaX X1-Hybrid-LV** (6 kW, serial prefix `HL1060`) over a local
Modbus RTU link, through a serial device server such as a Moxa NPort 5150A in TCP Server mode.
No cloud, no dependencies beyond Home Assistant.

## Devices and entities

Two devices, laid out like the SolaX cloud integration:

- **SolaX Local Inverter**: grid voltage/frequency/power; output power, current, today/total; solar
  power and string 1/2 voltage, current, power; backup (EPS) voltage, current, power, frequency;
  generator/V2L voltage, current, power, frequency; run mode, temperature; settings and codes
  (diagnostic); plus the controls below.
- **SolaX Local Battery**: SoC, voltage, current, power, temperature, charged/discharged today/total,
  cycles, max/min cell voltage and temperature, 16 cell voltages and 6 BMS temperatures (diagnostic).

Apparent power and power factor are diagnostic only: on the tested unit apparent power can read
slightly below active power, and the power factor stays at a fixed value.

Sign conventions: grid power positive = importing; battery power positive = charging.

## Controls (inverter settings)

Charge/discharge start and end times for periods 1-3, max charge/discharge power, and charge/discharge
stop SoC per period.

**These settings are stored in the inverter's EEPROM.** SolaX warns that frequent writes cause permanent
damage. The integration therefore:

- skips the write if the value is unchanged,
- refuses values outside the documented range (power capped at 6000 W),
- limits each setting to a number of writes per day (default 10, configurable in the options),
- reads the value back after every write and logs every change (see Download diagnostics).

Do not drive these controls from fast automations.

## Wiring and device-server settings

- Inverter `COM` port (RJ45): pin 4 RS485_A, pin 5 RS485_B, pin 6 GND.
- SolaX "A" is the positive line. On Moxa devices (Data+ = B) this means pin 4 -> DB9 pin 3 Data+(B),
  pin 5 -> DB9 pin 4 Data-(A), pin 6 -> DB9 pin 5 GND.
- Inverter LCD: Ex485 Modbus Baudrate 9600, Ex485 Modbus Address 1.
- Device server: RS-485 2-wire, 9600, 8 data bits, no parity, 1 stop bit, no flow control; TCP Server,
  local port 4001, max connection 1. Restrict access to the Home Assistant host.

## Register map

Based on SolaX "X1-Hybrid-Lv Modbus RTU V1.00" and "X1-Lite-Lv Modbus RTU Detailed V1.00", with every
address verified live on an HL1060 unit (firmware LVESS_V436.01). 32-bit values use big-endian word
order. Not available on this model: grid import/export and PV energy counters.

## Development

```
python -m venv .venv && .venv/bin/pip install pytest-homeassistant-custom-component
.venv/bin/python -m pytest
```

Tests run against a fake inverter that serves a captured register snapshot.
