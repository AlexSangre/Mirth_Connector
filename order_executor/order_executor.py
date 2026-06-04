"""
order_executor — watches /data/orders/ for JSON order files written by
the PerfusorOrders Mirth channel and applies them to the perfusor PLCs
via Modbus TCP.

Order JSON schema:
  {
    "order_id":  "ORD001",
    "patient_id": "GIZMO_PATIENT_001",
    "action":    "NW" | "CA",        NW = new order, CA = cancel
    "perfusor":  1 | 2 | 3,
    "drug":      "Morfina",
    "dose":      10,
    "dose_unit": "mg",
    "flujo":     30,                  mL/h mapped to perfusor_flujo register
    "timestamp": "2026-06-04T21:00:00Z"
  }

Register mapping (from plc_perfusor.conf):
  perfusor1_flujo  Holding @ 100   (0 = stop)
  perfusor2_flujo  Holding @ 101
  perfusor3_flujo  Holding @ 102

Flow:
  OpenEMR → MLLP → Mirth PerfusorOrders channel
    → /data/orders/order_*.json
      → order_executor reads, writes Holding register
        → plc_cerebro reads register every 5 s
          → cerebro sends MQTT command to physical perfusor actuator
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("order_executor")

ORDERS_DIR = Path(os.getenv("ORDERS_DIR", "/data/orders"))
ERRORS_DIR = Path(os.getenv("ERRORS_DIR", "/data/orders/errors"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "2"))   # check every 2 s
MODBUS_TIMEOUT = int(os.getenv("MODBUS_TIMEOUT", "5"))

PERFUSOR_PLC_IP = os.getenv("PERFUSOR_PLC_IP", "10.10.30.14")
PERFUSOR_PLC_PORT = int(os.getenv("PERFUSOR_PLC_PORT", "502"))
PERFUSOR_SLAVE_ID = int(os.getenv("PERFUSOR_SLAVE_ID", "3"))

# Holding register addresses per perfusor (from plc_perfusor.conf)
FLUJO_REGISTER: dict[int, int] = {1: 100, 2: 101, 3: 102}
MAX_FLUJO = 600  # hardware limit used by gizmo-brain.py


def _write_flujo(perfusor: int, flujo: int) -> None:
    address = FLUJO_REGISTER.get(perfusor)
    if address is None:
        raise ValueError(f"Unknown perfusor number: {perfusor}")

    flujo = max(0, min(flujo, MAX_FLUJO))

    client = ModbusTcpClient(PERFUSOR_PLC_IP, port=PERFUSOR_PLC_PORT, timeout=MODBUS_TIMEOUT)
    if not client.connect():
        raise ConnectionError(f"Cannot connect to perfusor PLC at {PERFUSOR_PLC_IP}:{PERFUSOR_PLC_PORT}")

    result = client.write_register(address, flujo, slave=PERFUSOR_SLAVE_ID)
    client.close()

    if result.isError():
        raise ModbusException(f"Write error on register {address}")

    log.info("Perfusor %d flujo set to %d mL/h (register %d)", perfusor, flujo, address)


def _process_order(order_file: Path) -> None:
    raw = order_file.read_text(encoding="utf-8")
    order: dict[str, Any] = json.loads(raw)

    order_id = order.get("order_id", "?")
    action   = order.get("action", "NW")
    perfusor = int(order.get("perfusor", 0))
    flujo    = int(order.get("flujo", 0))
    drug     = order.get("drug", "")

    log.info("Processing order %s: action=%s perfusor=%d drug=%s flujo=%d",
             order_id, action, perfusor, drug, flujo)

    if action == "CA":
        flujo = 0
        log.info("Cancel order — setting flujo=0 for perfusor %d", perfusor)

    _write_flujo(perfusor, flujo)
    order_file.unlink()  # delete after successful processing
    log.info("Order %s applied and removed", order_id)


def _move_to_errors(order_file: Path, exc: Exception) -> None:
    ERRORS_DIR.mkdir(parents=True, exist_ok=True)
    dest = ERRORS_DIR / order_file.name
    order_file.rename(dest)
    log.error("Order %s failed (%s) — moved to errors/", order_file.name, exc)


def run() -> None:
    ORDERS_DIR.mkdir(parents=True, exist_ok=True)
    log.info("order_executor started — watching %s every %ds", ORDERS_DIR, POLL_INTERVAL)

    while True:
        for order_file in sorted(ORDERS_DIR.glob("order_*.json")):
            try:
                _process_order(order_file)
            except Exception as exc:  # noqa: BLE001
                _move_to_errors(order_file, exc)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run()
