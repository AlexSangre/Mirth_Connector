"""
plc_exporter — polls all Modbus PLCs at POLL_INTERVAL and writes
a JSON snapshot to OUTPUT_DIR for Mirth Connect to pick up.

Environment variables:
  OUTPUT_DIR      Directory where JSON snapshots are written  (default: /data/plc_readings)
  POLL_INTERVAL   Polling cadence in seconds                  (default: 30)
  MODBUS_TIMEOUT  Modbus TCP connection timeout in seconds    (default: 5)
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import schedule
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

from devices import DEVICES, PLCDevice

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("plc_exporter")

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/data/plc_readings"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))
MODBUS_TIMEOUT = int(os.getenv("MODBUS_TIMEOUT", "5"))


def _read_device(device: PLCDevice) -> dict[str, Any]:
    readings: dict[str, int | bool | None] = {}
    errors: list[str] = []

    try:
        client = ModbusTcpClient(device.ip, port=device.port, timeout=MODBUS_TIMEOUT)
        if not client.connect():
            return {"readings": None, "errors": [f"Cannot connect to {device.ip}:{device.port}"]}

        for reg in device.holding_registers:
            result = client.read_holding_registers(reg.address, count=1, slave=device.slave_id)
            if result.isError():
                errors.append(f"{reg.name}: modbus read error")
                readings[reg.name] = None
            else:
                readings[reg.name] = result.registers[0]

        for coil in device.coil_registers:
            result = client.read_coils(coil.address, count=1, slave=device.slave_id)
            if result.isError():
                errors.append(f"{coil.name}: modbus read error")
                readings[coil.name] = None
            else:
                readings[coil.name] = bool(result.bits[0])

        client.close()

    except ModbusException as exc:
        return {"readings": None, "errors": [str(exc)]}

    return {
        "readings": readings,
        "errors": errors if errors else None,
    }


def poll_and_write() -> None:
    now = datetime.now(timezone.utc)
    timestamp_iso = now.isoformat()
    timestamp_file = now.strftime("%Y%m%dT%H%M%SZ")

    snapshot: dict[str, Any] = {
        "schema_version": "1.0",
        "timestamp": timestamp_iso,
        "source": "plc_exporter",
        "devices": {},
    }

    for device in DEVICES:
        log.info("Polling %s (%s)", device.name, device.ip)
        result = _read_device(device)
        snapshot["devices"][device.name] = {
            "ip": device.ip,
            "slave_id": device.slave_id,
            **result,
        }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"plc_snapshot_{timestamp_file}.json"
    output_file.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    log.info("Snapshot written: %s", output_file.name)


def _run_threaded(fn: Any) -> None:
    threading.Thread(target=fn, daemon=True).start()


if __name__ == "__main__":
    log.info("Starting PLC exporter — poll interval: %ds, output: %s", POLL_INTERVAL, OUTPUT_DIR)

    # immediate first poll so Mirth has data from the start
    poll_and_write()

    schedule.every(POLL_INTERVAL).seconds.do(_run_threaded, poll_and_write)

    while True:
        schedule.run_pending()
        time.sleep(1)
