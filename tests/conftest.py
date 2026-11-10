"""Test fixtures: a fake SolaX inverter behind an RTU-over-TCP device server."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import struct

import pytest

from custom_components.solax_lv_local.client import crc16

SNAPSHOT = Path(__file__).parent / "registers_snapshot.json"


class FakeInverter:
    """Serves Modbus RTU frames from a register snapshot; supports 0x03/0x04/0x06."""

    def __init__(self) -> None:
        raw = json.loads(SNAPSHOT.read_text())
        self.regs: dict[tuple[int, int], int] = {
            (int(k.split(":")[0]), int(k.split(":")[1])): v for k, v in raw.items()
        }
        self.writes: list[tuple[int, int]] = []
        self.requests = 0
        self.reject_writes = False
        self.server: asyncio.Server | None = None
        self.port = 0

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", self.port)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            self.server.close_clients()
            await self.server.wait_closed()
            self.server = None

    def _reply(self, unit: int, body: bytes) -> bytes:
        frame = bytes([unit]) + body
        return frame + crc16(frame)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                frame = await reader.readexactly(8)
                self.requests += 1
                assert crc16(frame[:6]) == frame[6:], "bad request CRC"
                unit, fc, addr, val = struct.unpack(">BBHH", frame[:6])
                if fc in (3, 4):
                    try:
                        values = [self.regs[(fc, addr + i)] for i in range(val)]
                    except KeyError:
                        writer.write(self._reply(unit, bytes([fc | 0x80, 2])))
                    else:
                        body = bytes([fc, 2 * val]) + struct.pack(f">{val}H", *values)
                        writer.write(self._reply(unit, body))
                elif fc == 6:
                    if self.reject_writes:
                        writer.write(self._reply(unit, bytes([0x86, 3])))
                    else:
                        self.regs[(3, addr)] = val
                        self.writes.append((addr, val))
                        writer.write(self._reply(unit, frame[1:6]))
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()


@pytest.fixture
async def fake_inverter(socket_enabled):
    inv = FakeInverter()
    await inv.start()
    yield inv
    await inv.stop()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
