# Mirth Connector — Gizmo Healthcare Digital Twin

Integration bridge between the OT/PLC layer and OpenEMR in the `gizmo-docker-twin-healthcare` digital twin environment.

## Overview

```
PLCs (Modbus TCP, 10.10.30.x)
        │
        ▼ every 30 s
 ┌─────────────────┐
 │  plc_exporter   │  Python · level1_plc (10.10.30.19)
 │  (pymodbus)     │  Polls 5 PLCs, writes JSON snapshot
 └────────┬────────┘
          │  Docker volume: plc_data
          ▼
 ┌─────────────────┐
 │  mirth-connect  │  NextGen Connect 4.4.1 · level3_operaciones (10.10.10.14)
 │  File Reader    │  Reads JSON → transforms to HL7 v2 ORU^R01 / FHIR Bundle
 │  File Writer    │  Stages .hl7 files in hl7_out volume
 │  HTTP Sender    │  (disabled) → OpenEMR FHIR API (10.10.10.16)
 └─────────────────┘
```

## Repository structure

```
Mirth_Connector/
├── docker-compose.yml              # plc_exporter + mirth-connect services
├── plc_exporter/
│   ├── Dockerfile
│   ├── requirements.txt            # pymodbus 3.7.4, schedule 1.2.2
│   ├── devices.py                  # PLC/register definitions (frozen dataclasses)
│   └── exporter.py                 # Main polling loop → JSON writer
└── mirth/
    └── channels/
        └── PLCtoOpenEMR.xml        # Importable Mirth Connect channel
```

## PLC devices polled

| Container | IP | Slave ID | Data |
|---|---|---|---|
| plc_signosvitales | 10.10.30.15 | 4 | Heart rate, BP systolic/diastolic, SpO2, resp. rate, temperature |
| plc_perfusor | 10.10.30.14 | 3 | Flow × 3, dose × 3, status × 3 |
| plc_cpap | 10.10.30.13 | 1 | Power, on/off status |
| plc_tac | 10.10.30.12 | 5 | Status, insert, scan, extract coils |
| plc_hospital | 10.10.30.17 | 2 | O2 tank, pressures (UCI/OR/TAC), generation panel, filters |

## JSON snapshot format

```json
{
  "schema_version": "1.0",
  "timestamp": "2026-06-04T21:00:00+00:00",
  "source": "plc_exporter",
  "devices": {
    "plc_signosvitales": {
      "ip": "10.10.30.15",
      "slave_id": 4,
      "readings": {
        "signosvitales_frecuencia": 72,
        "signosvitales_presion_baja": 80,
        "signosvitales_presion_alta": 120,
        "signosvitales_saturacion": 98,
        "signosvitales_rate": 16,
        "signosvitales_temp": 36
      },
      "errors": null
    }
  }
}
```

## Mirth Connect channel

**PLCtoOpenEMR.xml** provides two destinations:

| # | Name | Type | Default |
|---|---|---|---|
| 1 | Write HL7 ORU^R01 | File Writer → `/data/hl7_out/` | **Enabled** |
| 2 | Send to OpenEMR FHIR | HTTP POST → `10.10.10.16/apis/default/fhir/Observation` | **Disabled** |

The HL7 message includes LOINC-coded OBX segments for all vital signs. Enable destination 2 once the OpenEMR FHIR API is configured.

## Quick start

### Prerequisites

The parent environment must be running first:

```bash
cd gizmo-docker-twin-healthcare
docker compose up -d
```

### Start the Mirth connector

```bash
# From the gizmo-docker-twin-healthcare root:
docker compose -f docker-compose.yaml -f Mirth_Connector/docker-compose.yml up -d
```

Or from inside this folder (parent networks must already exist):

```bash
docker compose up -d
```

### Import the Mirth Connect channel

1. Open the Mirth Connect administrator: `https://localhost:8443`
2. Default credentials on first start: `admin / admin` (change immediately)
3. Go to **Channels → Import Channel**
4. Select `mirth/channels/PLCtoOpenEMR.xml`
5. Deploy the channel

### Verify plc_exporter

```bash
docker logs plc_exporter -f
# Expected:
# 2026-06-04 21:00:00 INFO plc_exporter: Polling plc_signosvitales (10.10.30.15)
# 2026-06-04 21:00:00 INFO plc_exporter: Snapshot written: plc_snapshot_20260604T210000Z.json
```

### Check JSON output

```bash
docker exec mirth-connect ls /data/plc_readings/
```

### Tune the polling interval

Set `POLL_INTERVAL` in `docker-compose.yml` under `plc_exporter.environment`. Default: `30` seconds.

## Connecting to OpenEMR

When ready to enable the FHIR push:

1. In the Mirth Connect administrator, edit the **PLCtoOpenEMR** channel
2. Enable **Destination 2: Send to OpenEMR FHIR**
3. Update credentials in the HTTP Sender properties if the OpenEMR `admin` password has changed
4. Redeploy the channel

OpenEMR FHIR API base: `http://10.10.10.16/apis/default/fhir/`

> Note: OpenEMR requires OAuth2 for the FHIR API in production. For the lab, basic auth is sufficient if the REST API is configured in `Administration → Globals → Connectors`.

## Environment variables — plc_exporter

| Variable | Default | Description |
|---|---|---|
| `OUTPUT_DIR` | `/data/plc_readings` | Directory for JSON snapshots |
| `POLL_INTERVAL` | `30` | Seconds between polls |
| `MODBUS_TIMEOUT` | `5` | Modbus TCP timeout (seconds) |

## Related repository

[gizmo-docker-twin-healthcare](https://gitlab.com/newlab-iot/general/gizmo-docker-twin-healthcare) — full digital twin environment.
