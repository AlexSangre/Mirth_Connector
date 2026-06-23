"""
device_exporter — polls healthcare-v2 REST APIs and writes normalized JSON
snapshots that Mirth Connect channels can consume (same volume/format convention
as plc_exporter, different file-name prefixes to avoid conflicts).

Device registry is in devices.py. This file never needs to change when a new
medical device is added to the integration.

Environment variables
---------------------
  <DeviceConfig.url_env>   Base URL for each registered device (see devices.py)
  OUTPUT_DIR               Timestamped snapshot directory  (default: /data/plc_readings)
  LATEST_DIR               latest.json directory           (default: /data/plc_latest)
  POLL_INTERVAL            Polling cadence in seconds      (default: 30)
  HTTP_TIMEOUT             Per-request timeout in seconds  (default: 5)
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

import requests
import schedule

from devices import DEVICES, DeviceConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("device_exporter")

OUTPUT_DIR    = Path(os.getenv("OUTPUT_DIR",   "/data/plc_readings"))
LATEST_DIR    = Path(os.getenv("LATEST_DIR",   "/data/plc_latest"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))
HTTP_TIMEOUT  = int(os.getenv("HTTP_TIMEOUT",  "5"))


def _url(device: DeviceConfig) -> str:
    return os.getenv(device.url_env, device.default_url)


def _fetch(url: str, name: str) -> dict[str, Any] | None:
    try:
        resp = requests.get(url, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        log.warning("Cannot reach %s (%s): %s", name, url, exc)
        return None


def _build_snapshot(device_key: str, status: str, readings: dict[str, Any] | None,
                    timestamp_iso: str, error: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "timestamp":      timestamp_iso,
        "source":         "device_exporter",
        "devices": {
            device_key: {
                "status":   status,
                "readings": readings,
                "errors":   [error] if error else None,
            }
        },
    }


def poll_and_write() -> None:
    now            = datetime.now(timezone.utc)
    timestamp_iso  = now.isoformat()
    timestamp_file = now.strftime("%Y%m%dT%H%M%SZ")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_DIR.mkdir(parents=True, exist_ok=True)

    for device in DEVICES:
        base_url = _url(device)
        raw      = _fetch(f"{base_url}{device.endpoint}", device.key)

        if raw is not None:
            readings = device.normalize(raw)
            status   = raw.get(device.status_field, "unknown") if device.status_field else "unknown"
            error    = None
        else:
            readings, status, error = None, "offline", "HTTP unreachable"

        payload  = json.dumps(
            _build_snapshot(device.key, status, readings, timestamp_iso, error),
            indent=2,
        )
        out_file = OUTPUT_DIR / f"{device.file_prefix}_{timestamp_file}.json"
        out_file.write_text(payload, encoding="utf-8")
        log.info("%s snapshot → %s", device.key, out_file.name)

        if device.write_latest:
            (LATEST_DIR / "latest.json").write_text(payload, encoding="utf-8")


def _run_threaded(fn: Any) -> None:
    threading.Thread(target=fn, daemon=True).start()


if __name__ == "__main__":
    device_list = ", ".join(f"{d.key}={_url(d)}" for d in DEVICES)
    log.info(
        "Starting device_exporter | interval=%ds | devices: [%s]",
        POLL_INTERVAL, device_list,
    )

    poll_and_write()

    schedule.every(POLL_INTERVAL).seconds.do(_run_threaded, poll_and_write)

    while True:
        schedule.run_pending()
        time.sleep(1)
