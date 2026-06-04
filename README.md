# Mirth Connector — Gizmo Healthcare Digital Twin

Integration bridge between the OT/PLC layer, Orthanc PACS, and OpenEMR in the `gizmo-docker-twin-healthcare` digital twin environment.

## Architecture

```
┌──────────────────────── level1_plc (10.10.30.x) ────────────────────────┐
│                                                                          │
│  plc_signosvitales (10.10.30.15)  plc_perfusor (10.10.30.14)            │
│  plc_cpap          (10.10.30.13)  plc_tac      (10.10.30.12)            │
│  plc_hospital      (10.10.30.17)                                         │
│        │ Modbus TCP                     ▲ Modbus write                   │
│        ▼ every 30 s                     │                                │
│  ┌─────────────┐              ┌──────────────────┐                       │
│  │ plc_exporter│              │  order_executor  │                       │
│  │ 10.10.30.19 │              │  10.10.30.20     │                       │
│  └──────┬──────┘              └────────▲─────────┘                       │
│         │ plc_data + plc_latest vols   │ orders_data vol                 │
└─────────┼──────────────────────────────┼─────────────────────────────────┘
          │                              │
┌─────────┼──────── level3_operaciones (10.10.10.x) ──────────────────────┐
│         ▼                              │                                 │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │                    mirth-connect  (10.10.10.14)                  │    │
│  │                                                                  │    │
│  │  Ch 1 PLCtoOpenEMR      File Reader → HL7 ORU^R01 vital signs   │    │
│  │  Ch 2 OrthancToOpenEMR  JS polls Orthanc → HL7 ORU^R01 DICOM    │    │
│  │  Ch 3 VitalSignsAlerts  JS reads latest.json → alert ORU^R01    │    │
│  │  Ch 4 PerfusorOrders    MLLP:6661 ORM^O01 → order JSON ─────────┼────┘
│  └──────────────────────────────┬───────────────────────────────────┘
│                                 │ hl7_out vol / HTTP FHIR
│  OpenEMR (10.10.10.16) ◄────────┘    Orthanc (10.10.10.15)
│
│  TAC scan (gizmo-brain.py → send_dicom.py):
│    ├─► DICOM C-STORE ──────────────────────────────► Orthanc :4242
│    └─► Orthanc /changes polled by Ch 2 ──────────── HL7 → OpenEMR
└─────────────────────────────────────────────────────────────────────────┘
```

## Services

| Container | IP | Network | Role |
|---|---|---|---|
| `plc_exporter` | 10.10.30.19 | level1_plc | Polls PLCs every 30 s → JSON |
| `order_executor` | 10.10.30.20 | level1_plc | Reads orders → Modbus write → perfusor PLC |
| `mirth-connect` | 10.10.10.14 | level3_operaciones | HL7/FHIR integration hub |

## Channels

| # | Name | Source | Output | Default |
|---|---|---|---|---|
| 1 | PLCtoOpenEMR | File Reader `/data/plc_readings/` | HL7 ORU^R01 vital signs | Enabled |
| 2 | OrthancToOpenEMR | JS polls `http://10.10.10.15:8042/changes` | HL7 ORU^R01 DICOM ref | Enabled |
| 3 | VitalSignsAlerts | JS reads `/data/plc_latest/latest.json` | HL7 ORU^R01 w/ HH/LL flags | Enabled |
| 4 | PerfusorOrders | MLLP Listener :6661 ORM^O01 | JSON order → `/data/orders/` | Enabled |

## Repository structure

```
Mirth_Connector/
├── docker-compose.yml
├── plc_exporter/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── devices.py              PLC/register definitions
│   └── exporter.py             Modbus polling → plc_data + plc_latest volumes
├── order_executor/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── order_executor.py       Watches orders volume → Modbus write to perfusor PLC
└── mirth/
    └── channels/
        ├── PLCtoOpenEMR.xml        Channel 1
        ├── OrthancToOpenEMR.xml    Channel 2
        ├── VitalSignsAlerts.xml    Channel 3
        └── PerfusorOrders.xml      Channel 4
```

---

## Channel 3 — VitalSignsAlerts

Evaluates ICU vital signs against clinical thresholds every 30 s. Generates an HL7 ORU^R01 **only when at least one value is out of range** — no alert, no message.

**Thresholds:**

| Parameter | LL (critical low) | L (low) | H (high) | HH (critical high) |
|---|---|---|---|---|
| Heart rate | < 30 bpm | < 50 | > 120 | > 150 |
| SpO2 | < 85 % | < 90 | — | — |
| Systolic BP | < 70 mmHg | < 90 | > 140 | > 180 |
| Diastolic BP | < 40 mmHg | < 60 | > 95 | > 120 |
| Temperature | < 35 °C | < 36 | > 38 | > 40 |
| Respiratory rate | < 5 /min | < 10 | > 25 | > 35 |

**HL7 output example (SpO2 critically low):**

```
MSH|^~\&|PLC_ALERTS|HOSPITAL_GIZMO|MIRTH_CONNECT|OPENEMR|20260604210000||ORU^R01|ALERT20260604210000|P|2.5.1|||AL|AL|
PID|1||GIZMO_PATIENT_001^^^...
OBR|1||CRITICAL_20260604210000|85353-1^Vital signs panel^LN|||...|||F
OBX|4|NM|59408-5^Oxygen saturation^LN||87|%|90-100|LL|||F|||20260604210000||LL^CRITICAL
ZAL|CRITICAL|saturacion=87[LL]|2026-06-04T21:00:00Z
```

---

## Channel 4 — PerfusorOrders (MLLP Hub)

Receives HL7 ORM^O01 from OpenEMR on port **6661** and routes infusion orders to the perfusor PLCs.

**Medication → Perfusor mapping:**

| Perfusor | Medications |
|---|---|
| 1 | Morfina, Morphine, Fentanilo, Fentanyl |
| 2 | Noradrenalina, Norepinephrine, Dopamina |
| 3 | Propofol, Midazolam, Ketamina |

**Order execution flow:**

```
OpenEMR creates medication order
  └─► HL7 ORM^O01 via MLLP → Mirth :6661
        └─► PerfusorOrders transformer parses:
              ORC.1 = NW (new) / CA (cancel)
              RXO.1 = drug name → maps to perfusor 1/2/3
              TQ1.7 = rate mL/h → flujo value
        └─► /data/orders/order_{ts}.json
              └─► order_executor every 2 s:
                    write_register(perfusor_flujo, rate)
                    └─► plc_cerebro reads every 5 s
                          └─► MQTT command to physical actuator
```

**Test order from command line:**

```bash
# Requires netcat (nc) and MLLP framing
printf "\x0bMSH|^~\&|OPENEMR|HOSPITAL|MIRTH|PLC|$(date +%Y%m%d%H%M%S)||ORM^O01|TEST001|P|2.5.1\rPID|1||GIZMO_PATIENT_001\rORC|NW|ORD001\rRXO|Morfina^^LOCAL|10|mg|IV\rTQ1|1|||30|mL/h\x1c\r" | nc 127.0.0.1 6661
```

**Cancel order:**
```bash
# ORC.1 = CA → sets flujo = 0 (stops infusion)
printf "\x0bMSH|...|ORM^O01|TEST002|P|2.5.1\rORC|CA|ORD001\rRXO|Morfina^^LOCAL\rTQ1|1|||0|mL/h\x1c\r" | nc 127.0.0.1 6661
```

---

## Quick start

### Prerequisites

```bash
cd gizmo-docker-twin-healthcare
docker compose up -d
```

### Start the Mirth connector

```bash
# From gizmo-docker-twin-healthcare root:
docker compose -f docker-compose.yaml -f Mirth_Connector/docker-compose.yml up -d
```

### Import all Mirth channels

1. Open `https://localhost:8443` (default: `admin / admin`)
2. **Channels → Import Channel**, import in order:
   1. `mirth/channels/PLCtoOpenEMR.xml`
   2. `mirth/channels/OrthancToOpenEMR.xml`
   3. `mirth/channels/VitalSignsAlerts.xml`
   4. `mirth/channels/PerfusorOrders.xml`
3. Deploy all channels

### Verify

```bash
# plc_exporter polling
docker logs plc_exporter -f

# order_executor watching orders
docker logs order_executor -f

# Check HL7 output (all channels write here)
docker exec mirth-connect ls /data/hl7_out/

# Check orders volume
docker exec order_executor ls /data/orders/
```

## Enabling OpenEMR FHIR integration

All channels have a disabled HTTP Sender destination pre-configured for `10.10.10.16`. When ready:

1. Enable **Destination 2** in any channel
2. Ensure OpenEMR REST API is enabled: `Administration → Globals → Connectors`
3. Redeploy the channel

## Environment variables

**plc_exporter:**

| Variable | Default | Description |
|---|---|---|
| `OUTPUT_DIR` | `/data/plc_readings` | Timestamped snapshots |
| `LATEST_DIR` | `/data/plc_latest` | Overwritten latest.json |
| `POLL_INTERVAL` | `30` | Seconds between polls |
| `MODBUS_TIMEOUT` | `5` | Modbus TCP timeout |

**order_executor:**

| Variable | Default | Description |
|---|---|---|
| `ORDERS_DIR` | `/data/orders` | Directory to watch |
| `POLL_INTERVAL` | `2` | Check interval (seconds) |
| `PERFUSOR_PLC_IP` | `10.10.30.14` | Perfusor PLC address |
| `PERFUSOR_SLAVE_ID` | `3` | Modbus slave ID |

## Related repository

[gizmo-docker-twin-healthcare](https://gitlab.com/newlab-iot/general/gizmo-docker-twin-healthcare) — full digital twin environment.
