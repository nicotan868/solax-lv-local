"""Minimal async Modbus RTU-over-TCP client (no external dependencies).

The SolaX X1-Hybrid-LV sits behind a transparent serial device server (e.g. Moxa
NPort in TCP Server mode), so frames on the socket are plain Modbus RTU with CRC.
"""

from __future__ import annotations

import asyncio
import logging
import struct

_LOGGER = logging.getLogger(__name__)

FC_READ_HOLDING = 0x03
FC_READ_INPUT = 0x04
FC_WRITE_SINGLE = 0x06


class ModbusError(Exception):
    """Communication or protocol error."""


class ModbusExceptionResponse(ModbusError):
    """The device answered with a Modbus exception code."""

    def __init__(self, function: int, code: int) -> None:
        super().__init__(f"Modbus exception {code} for function {function:#04x}")
        self.code = code


def crc16(data: bytes) -> bytes:
    """Modbus RTU CRC16, little endian."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return struct.pack("<H", crc)


class RtuOverTcpClient:
    """Serialised request/response client with automatic reconnect."""

    def __init__(
        self,
        host: str,
        port: int,
        unit_id: int = 1,
        timeout: float = 3.0,
        request_gap: float = 0.05,
    ) -> None:
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self.request_gap = request_gap
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def _connect(self) -> None:
        if self.connected:
            return
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.timeout
            )
        except (OSError, TimeoutError) as err:
            self._reader = self._writer = None
            raise ModbusError(f"Cannot connect to {self.host}:{self.port}: {err}") from err

    async def close(self) -> None:
        async with self._lock:
            await self._close()

    async def _close(self) -> None:
        writer, self._reader, self._writer = self._writer, None, None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def _transact(self, pdu: bytes, expected_len: int) -> bytes:
        """Send one RTU frame and return the validated response (without CRC)."""
        async with self._lock:
            for attempt in (1, 2):
                try:
                    await self._connect()
                    assert self._reader is not None and self._writer is not None
                    # Drop any stale bytes left from an earlier timed-out request.
                    while True:
                        try:
                            stale = await asyncio.wait_for(self._reader.read(256), 0.001)
                        except TimeoutError:
                            break
                        if not stale:
                            raise ModbusError("Connection closed by peer")
                    frame = bytes([self.unit_id]) + pdu
                    self._writer.write(frame + crc16(frame))
                    await self._writer.drain()
                    resp = await asyncio.wait_for(
                        self._read_response(pdu[0], expected_len), self.timeout
                    )
                    await asyncio.sleep(self.request_gap)
                    return resp
                except ModbusExceptionResponse:
                    await asyncio.sleep(self.request_gap)
                    raise
                except (ModbusError, OSError, TimeoutError) as err:
                    await self._close()
                    if attempt == 2:
                        raise ModbusError(str(err) or type(err).__name__) from err
                    _LOGGER.debug("Retrying after error: %s", err)
            raise ModbusError("unreachable")

    async def _read_response(self, function: int, expected_len: int) -> bytes:
        assert self._reader is not None
        head = await self._reader.readexactly(2)
        if head[0] != self.unit_id:
            raise ModbusError(f"Unexpected unit id {head[0]}")
        if head[1] == function | 0x80:
            rest = await self._reader.readexactly(3)
            frame = head + rest
            if crc16(frame[:-2]) != frame[-2:]:
                raise ModbusError("Bad CRC in exception response")
            raise ModbusExceptionResponse(function, rest[0])
        if head[1] != function:
            raise ModbusError(f"Unexpected function {head[1]:#04x}")
        rest = await self._reader.readexactly(expected_len - 2)
        frame = head + rest
        if crc16(frame[:-2]) != frame[-2:]:
            raise ModbusError("Bad CRC")
        return frame[:-2]

    async def read_registers(self, function: int, address: int, count: int) -> list[int]:
        """Read `count` registers with function 0x03 or 0x04."""
        if not 1 <= count <= 125:
            raise ValueError("count must be 1..125")
        pdu = struct.pack(">BHH", function, address, count)
        resp = await self._transact(pdu, 5 + 2 * count)
        if resp[2] != 2 * count:
            raise ModbusError("Unexpected byte count")
        return list(struct.unpack(f">{count}H", resp[3 : 3 + 2 * count]))

    async def read_input(self, address: int, count: int) -> list[int]:
        return await self.read_registers(FC_READ_INPUT, address, count)

    async def read_holding(self, address: int, count: int) -> list[int]:
        return await self.read_registers(FC_READ_HOLDING, address, count)

    async def write_register(self, address: int, value: int) -> None:
        """Write one holding register (function 0x06); the device echoes the request."""
        if not 0 <= value <= 0xFFFF:
            raise ValueError("value out of 16-bit range")
        pdu = struct.pack(">BHH", FC_WRITE_SINGLE, address, value)
        resp = await self._transact(pdu, 8)
        if resp[1:] != pdu:
            raise ModbusError("Write echo mismatch")
