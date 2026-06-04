"""
PLC device and register definitions for the Gizmo Healthcare digital twin.
All addresses match the .conf files under config/plc/ in gizmo-docker-twin-healthcare.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HoldingRegister:
    name: str
    address: int


@dataclass(frozen=True)
class CoilRegister:
    name: str
    address: int


@dataclass(frozen=True)
class PLCDevice:
    name: str
    ip: str
    port: int
    slave_id: int
    holding_registers: tuple[HoldingRegister, ...]
    coil_registers: tuple[CoilRegister, ...]


DEVICES: tuple[PLCDevice, ...] = (
    PLCDevice(
        name="plc_signosvitales",
        ip="10.10.30.15",
        port=502,
        slave_id=4,
        holding_registers=(
            HoldingRegister("signosvitales_frecuencia", 100),   # heart rate (bpm)
            HoldingRegister("signosvitales_presion_baja", 101), # diastolic BP (mmHg)
            HoldingRegister("signosvitales_presion_alta", 102), # systolic BP (mmHg)
            HoldingRegister("signosvitales_saturacion", 103),   # SpO2 (%)
            HoldingRegister("signosvitales_rate", 104),         # respiratory rate (/min)
            HoldingRegister("signosvitales_temp", 105),         # body temperature (°C x10)
        ),
        coil_registers=(),
    ),
    PLCDevice(
        name="plc_perfusor",
        ip="10.10.30.14",
        port=502,
        slave_id=3,
        holding_registers=(
            HoldingRegister("perfusor1_flujo", 100),
            HoldingRegister("perfusor2_flujo", 101),
            HoldingRegister("perfusor3_flujo", 102),
            HoldingRegister("perfusor1_dosis", 103),
            HoldingRegister("perfusor2_dosis", 104),
            HoldingRegister("perfusor3_dosis", 105),
        ),
        coil_registers=(
            CoilRegister("perfusor1_status", 100),
            CoilRegister("perfusor2_status", 101),
            CoilRegister("perfusor3_status", 102),
        ),
    ),
    PLCDevice(
        name="plc_cpap",
        ip="10.10.30.13",
        port=502,
        slave_id=1,
        holding_registers=(
            HoldingRegister("cpap_potencia", 100),
        ),
        coil_registers=(
            CoilRegister("cpap_status", 100),
        ),
    ),
    PLCDevice(
        name="plc_tac",
        ip="10.10.30.12",
        port=502,
        slave_id=5,
        holding_registers=(),
        coil_registers=(
            CoilRegister("tac_status", 100),
            CoilRegister("tac_insert", 101),
            CoilRegister("tac_scan", 102),
            CoilRegister("tac_extract", 103),
        ),
    ),
    PLCDevice(
        name="plc_hospital",
        ip="10.10.30.17",
        port=502,
        slave_id=2,
        holding_registers=(
            HoldingRegister("hospital_tanque", 100),
            HoldingRegister("hospital_oxigeno_tanque", 101),
            HoldingRegister("hospital_panel_generacion", 102),
            HoldingRegister("hospital_oxigeno_reserva", 103),
            HoldingRegister("hospital_presion_uci", 104),
            HoldingRegister("hospital_presion_quirofano", 105),
            HoldingRegister("hospital_presion_tac", 106),
            HoldingRegister("hospital_oxigeno_tanque_set", 107),
        ),
        coil_registers=(
            CoilRegister("hospital_filtro", 100),
            CoilRegister("hospital_redistribucion", 101),
            CoilRegister("hospital_iluminacion_status", 102),
            CoilRegister("hospital_generador_status", 103),
        ),
    ),
)
