"""
Medical device registry for device_exporter.

Adding a new device requires only:
  1. A _normalize_<device> function mapping the REST API response to a flat readings dict.
  2. A DeviceConfig entry appended to DEVICES.
  3. A matching env var in docker-compose.healthcare.yml.
  4. A new Mirth channel XML consuming <file_prefix>_snapshot_*.json.

exporter.py never changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class DeviceConfig:
    key: str                                             # device key in snapshot JSON
    url_env: str                                         # env var holding the base URL
    default_url: str                                     # fallback when env var is absent
    file_prefix: str                                     # e.g. "vitals_snapshot" → vitals_snapshot_*.json
    endpoint: str                                        # path appended to base URL, e.g. "/state"
    status_field: str | None                             # top-level field in API response for status
    normalize: Callable[[dict[str, Any]], dict[str, Any]]
    write_latest: bool = False                           # also overwrite LATEST_DIR/latest.json


# ---------------------------------------------------------------------------
# Normalizers — map raw API response shapes to flat readings dicts
# ---------------------------------------------------------------------------

def _normalize_vitals(data: dict[str, Any]) -> dict[str, Any]:
    """
    PatientMonitor.snapshot() returns signals as {"heart_rate": {"value": X, "unit": Y}, ...}
    Map to plc_signosvitales field names so VitalSignsAlerts channel works unchanged.
    """
    signals = data.get("signals", {})

    def val(key: str) -> Any:
        s = signals.get(key)
        return s["value"] if isinstance(s, dict) else None

    return {
        "signosvitales_frecuencia":   val("heart_rate"),
        "signosvitales_saturacion":   val("spo2"),
        "signosvitales_presion_alta": val("systolic_bp"),
        "signosvitales_presion_baja": val("diastolic_bp"),
        "signosvitales_temp":         val("temperature"),
        "signosvitales_rate":         val("respiratory_rate"),
    }


def _normalize_cpap(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "therapy_status":        data.get("therapy_status"),
        "mode":                  data.get("mode"),
        "pressure_set_cmh2o":    data.get("pressure_set_cmh2o"),
        "peep_cmh2o":            data.get("peep_cmh2o"),
        "actual_pressure_cmh2o": data.get("actual_pressure_cmh2o"),
        "flow_l_min":            data.get("actual_flow_l_min"),
        "measured_tidal_vol_ml": data.get("measured_tidal_vol_ml"),
        "fio2_set_pct":          data.get("fio2_set_pct"),
        "actual_fio2_pct":       data.get("actual_fio2_pct"),
        "respiratory_rate_bpm":  data.get("respiratory_rate_bpm"),
        "leak_percentage":       data.get("leak_percentage"),
        "total_cycles":          data.get("total_cycles"),
        "therapy_time_s":        data.get("therapy_time_s"),
    }


def _normalize_crrt(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "therapy_status":            data.get("therapy_status"),
        "mode":                      data.get("mode"),
        "blood_flow_ml_min":         data.get("blood_flow_ml_min"),
        "dialysate_flow_ml_h":       data.get("dialysate_flow_ml_h"),
        "replacement_flow_ml_h":     data.get("replacement_flow_ml_h"),
        "uf_target_ml_h":            data.get("uf_target_ml_h"),
        "tmp_mmhg":                  data.get("tmp_mmhg"),
        "access_pressure_mmhg":      data.get("access_pressure_mmhg"),
        "return_pressure_mmhg":      data.get("return_pressure_mmhg"),
        "prefilter_pressure_mmhg":   data.get("prefilter_pressure_mmhg"),
        "postfilter_pressure_mmhg":  data.get("postfilter_pressure_mmhg"),
        "vol_uf_ml":                 data.get("vol_uf_ml"),
        "net_balance_ml":            data.get("net_balance_ml"),
        "filter_runtime_h":          data.get("filter_runtime_h"),
        "filter_saturation_pct":     data.get("filter_saturation_pct"),
        "filter_life_remaining_pct": data.get("filter_life_remaining_pct"),
        "heparin_iu_h":              data.get("heparin_iu_h"),
    }


def _normalize_infusion_pump(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "infusion_active":         data.get("infusion_active"),
        "kvo_mode":                data.get("kvo_mode"),
        "flow_rate_ml_h":          data.get("flow_rate_ml_h"),
        "vtbi_ml":                 data.get("vtbi_ml"),
        "infused_volume_ml":       data.get("infused_volume_ml"),
        "drops_per_ml":            data.get("drops_per_ml"),
        "drop_rate_per_min":       data.get("drop_rate_per_min"),
        "pressure_kpa":            data.get("pressure_kpa"),
        "occlusion_threshold_kpa": data.get("occlusion_threshold_kpa"),
        "bubble_detected":         data.get("bubble_detected"),
        "motor_running":           data.get("motor_running"),
        "door_open":               data.get("door_open"),
        "battery_voltage_v":       data.get("battery_voltage_v"),
        "battery_remaining_min":   data.get("battery_remaining_min"),
        "on_battery":              data.get("on_battery"),
        "alarm_mask":              data.get("alarm_mask"),
        "alarm_flags":             data.get("alarm_flags"),
    }


# ---------------------------------------------------------------------------
# Device registry
# ---------------------------------------------------------------------------

DEVICES: tuple[DeviceConfig, ...] = (
    DeviceConfig(
        key          = "plc_signosvitales",
        url_env      = "VITALS_URL",
        default_url  = "http://10.10.30.12:8000",
        file_prefix  = "vitals_snapshot",
        endpoint     = "/state",
        status_field = "status",
        normalize    = _normalize_vitals,
    ),
    DeviceConfig(
        key          = "cpap",
        url_env      = "CPAP_URL",
        default_url  = "http://10.10.30.11:8000",
        file_prefix  = "cpap_snapshot",
        endpoint     = "/state",
        status_field = "therapy_status",
        normalize    = _normalize_cpap,
    ),
    DeviceConfig(
        key          = "crrt",
        url_env      = "CRRT_URL",
        default_url  = "http://10.10.30.10:8000",
        file_prefix  = "crrt_snapshot",
        endpoint     = "/state",
        status_field = "therapy_status",
        normalize    = _normalize_crrt,
    ),
    DeviceConfig(
        key          = "infusion_pump",
        url_env      = "INFUSION_PUMP_URL",
        default_url  = "http://10.10.30.13:8000",
        file_prefix  = "infusion_snapshot",
        endpoint     = "/pumps/PUMP-GENERIC-001/state",
        status_field = "status",          # "infusing" | "kvo" | "standby" (set by api.py)
        normalize    = _normalize_infusion_pump,
    ),
    # -------------------------------------------------------------------------
    # To add a new device:
    #   1. Define _normalize_<device>(data) above.
    #   2. Append a DeviceConfig here.
    #   3. Add <DEVICE.url_env>: "http://..." to docker-compose.healthcare.yml.
    #   4. Create mirth/channels/<Device>toHL7.xml consuming <file_prefix>_snapshot_*.json.
    # -------------------------------------------------------------------------
)
