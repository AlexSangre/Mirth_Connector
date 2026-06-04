# Mirth Connector — Gizmo Healthcare Digital Twin

Integration bridge between the OT/PLC layer, Orthanc PACS, and OpenEMR in the `gizmo-docker-twin-healthcare` digital twin environment.

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
 ┌─────────────────────────────────────────────────────────┐
 │                    mirth-connect                        │
 │              NextGen Connect 4.4.1                      │
 │          level3_operaciones (10.10.10.14)               │
 │                                                         │
 │  Channel 1 — PLCtoOpenEMR                               │
 │    File Reader (plc_data) → HL7 ORU^R01 (vital signs)   │
 │    File Writer → /data/hl7_out/                         │
 │    HTTP Sender → OpenEMR FHIR /Observation (disabled)   │
 │                                                         │
 │  Channel 2 — OrthancToOpenEMR                           │
 │    JS Reader polls Orthanc /changes every 30 s          │
 │    New study detected → HL7 ORU^R01 (DICOM reference)   │
 │    File Writer → /data/hl7_out/                         │
 │    HTTP Sender → OpenEMR FHIR /ImagingStudy (disabled)  │
 └─────────────────────────────────────────────────────────┘

TAC scan event (gizmo-brain.py → send_dicom.py):
  ├─► DICOM C-STORE ──────────────► Orthanc (10.10.10.15:4242)  [direct, unchanged]
  └─► Orthanc /changes polled ────► Channel 2 detects new study → HL7 → OpenEMR
```

## Repository structure

```
Mirth_Connector/
├── docker-compose.yml
├── plc_exporter/
│   ├── Dockerfile
│   ├── requirements.txt            # pymodbus 3.7.4, schedule 1.2.2
│   ├── devices.py                  # PLC/register definitions (frozen dataclasses)
│   └── exporter.py                 # Modbus polling loop → JSON writer
└── mirth/
    └── channels/
        ├── PLCtoOpenEMR.xml        # Channel 1: vital signs JSON → HL7 ORU^R01
        └── OrthancToOpenEMR.xml    # Channel 2: Orthanc DICOM study → HL7 ORU^R01
```

## Channel 1 — PLCtoOpenEMR

Reads JSON snapshots from `plc_exporter` and transforms vital signs to HL7.

**PLC devices polled:**

| Container | IP | Slave ID | Data |
|---|---|---|---|
| plc_signosvitales | 10.10.30.15 | 4 | Heart rate, BP systolic/diastolic, SpO2, resp. rate, temperature |
| plc_perfusor | 10.10.30.14 | 3 | Flow × 3, dose × 3, status × 3 |
| plc_cpap | 10.10.30.13 | 1 | Power, on/off status |
| plc_tac | 10.10.30.12 | 5 | Status, insert, scan, extract coils |
| plc_hospital | 10.10.30.17 | 2 | O2 tank, pressures (UCI/OR/TAC), generation panel, filters |

**JSON snapshot format:**

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

**Destinations:**

| # | Name | Type | Default |
|---|---|---|---|
| 1 | Write HL7 ORU^R01 | File Writer → `/data/hl7_out/` | **Enabled** |
| 2 | Send to OpenEMR FHIR | HTTP POST → `/fhir/Observation` | **Disabled** |

## Channel 2 — OrthancToOpenEMR

Detects new DICOM studies in Orthanc and sends an HL7 notification to OpenEMR.

**Flow:**

```
tac_scan coil changes (plc_tac, gizmo-brain.py)
  └─► send_dicom.py runs on kali-rolling (10.10.30.60)
        ├─► DICOM C-STORE ──► Orthanc (10.10.10.15:4242)   ← image stored
        └─► [no change needed to send_dicom.py]

Channel 2 (every 30 s):
  GET http://10.10.10.15:8042/changes?since={last_seq}
  └─ ChangeType == NewStudy?
       └─► GET /studies/{id} → fetch metadata
             └─► HL7 ORU^R01 with StudyInstanceUID + Orthanc viewer URL
                   └─► /data/hl7_out/DICOM_ORU_*.hl7
```

**HL7 OBX segments generated:**

| OBX | LOINC | Content |
|---|---|---|
| 1 | 110180-7 | StudyInstanceUID + Orthanc endpoint |
| 2 | 59847-4 | Modality (CT / MR / XA) |
| 3 | 32484-8 | Study description |
| 4 | 113014 | Direct Orthanc viewer URL |

**Destinations:**

| # | Name | Type | Default |
|---|---|---|---|
| 1 | Write HL7 ORU^R01 DICOM | File Writer → `/data/hl7_out/` | **Enabled** |
| 2 | Send to OpenEMR FHIR | HTTP POST → `/fhir/ImagingStudy` | **Disabled** |

The channel uses `globalChannelMap` to track the last processed Orthanc change sequence, so it never reprocesses studies across restarts.

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

### Import Mirth Connect channels

1. Open the Mirth Connect administrator: `https://localhost:8443`
2. Default credentials on first start: `admin / admin` (change immediately)
3. Go to **Channels → Import Channel**
4. Import both channels:
   - `mirth/channels/PLCtoOpenEMR.xml`
   - `mirth/channels/OrthancToOpenEMR.xml`
5. Deploy both channels

### Verify plc_exporter

```bash
docker logs plc_exporter -f
# 2026-06-04 21:00:00 INFO plc_exporter: Polling plc_signosvitales (10.10.30.15)
# 2026-06-04 21:00:00 INFO plc_exporter: Snapshot written: plc_snapshot_20260604T210000Z.json
```

### Trigger a TAC scan and verify the DICOM channel

```bash
# Trigger the scan from RapidSCADA or directly via Modbus
# Then check Orthanc received the study:
curl http://localhost:8042/studies

# Check Mirth detected it (Mirth admin → Channel 2 → Dashboard)
# Check the HL7 output:
docker exec mirth-connect ls /data/hl7_out/
```

## Connecting to OpenEMR

When ready to enable the FHIR push for either channel:

1. In the Mirth Connect administrator, edit the channel
2. Enable **Destination 2** (HTTP Sender)
3. Verify credentials match the OpenEMR `admin` account
4. Redeploy the channel

OpenEMR FHIR API base: `http://10.10.10.16/apis/default/fhir/`

> Note: OpenEMR requires OAuth2 for the FHIR API in production. For the lab,
> basic auth is sufficient if the REST API is configured in
> `Administration → Globals → Connectors`.

## Environment variables — plc_exporter

| Variable | Default | Description |
|---|---|---|
| `OUTPUT_DIR` | `/data/plc_readings` | Directory for JSON snapshots |
| `POLL_INTERVAL` | `30` | Seconds between polls |
| `MODBUS_TIMEOUT` | `5` | Modbus TCP timeout (seconds) |

## Related repository

[gizmo-docker-twin-healthcare](https://gitlab.com/newlab-iot/general/gizmo-docker-twin-healthcare) — full digital twin environment.
