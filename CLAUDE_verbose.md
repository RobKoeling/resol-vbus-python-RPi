# resol-vbus-python: Project Overview for Claude

## Project Purpose

This is a Python application for reading RESOL VBUS (heating/solar system protocol) data from solar heating systems. It provides:

1. **Core Parser** - Decodes VBUS protocol messages from RESOL devices (e.g., DeltaSol solar controllers)
2. **Data Collector** - Continuous daemon that periodically captures and stores parsed data in SQLite
3. **Web UI** - Flask web interface displaying real-time and historical solar system data
4. **Systemd Integration** - Can be deployed as systemd services on Raspberry Pi or Linux

### Key Use Case
Monitor a solar heating system installation and display current temperatures, pump states, and other metrics on a web dashboard.

---

## Directory Structure

```
resol-vbus-python/
├── resol.py                 # Main VBUS parser (reads stream, decodes PV1/PV2/PV3, outputs JSON)
├── parser.py                # Reusable parsing library (parse_raw_bytes() function)
├── config.py                # Runtime configuration (connection type, ports, spec file, etc.)
├── spec.py                  # Loads JSON spec file from RESOL spec directory
├── db.py                    # SQLite database manager (snapshots table, measurements table)
├── capture_device.py        # Utility to capture raw VBUS data to files (manual/periodic)
├── collector.py             # Continuous background collector daemon
├── requirements.txt         # Python dependencies (Flask, pyserial, pytest)
│
├── ui/                      # Flask web UI
│   ├── app.py              # Flask app with routes (index, under_construction)
│   ├── run_server.py       # CLI helper to start Flask with LAN IP detection
│   ├── live_reader.py      # Background thread for continuous serial polling
│   ├── seed_sample_db.py   # Helper to populate sample data in SQLite
│   ├── templates/
│   │   ├── base.html       # Layout with sidebar navigation
│   │   └── status.html     # Current status view
│   ├── static/
│   │   └── style.css       # UI styling
│   ├── SYSTEMD_UI.md       # Instructions for running UI as systemd service
│   └── __pycache__/
│
├── systemd/                 # Systemd unit files
│   ├── resol-collector.service   # Collector daemon unit
│   ├── resol-ui.service          # Flask UI service
│   └── resol-ui.service.template # Template (needs customization)
│
├── spec/                    # RESOL device specifications (JSON-converted from XML)
│   ├── DeltaSolSLL.json    # Primary spec for DeltaSol SLL controller
│   ├── DeltaSolBS2009.json
│   ├── DeltaSolBXPlus.json
│   ├── CitrinSLRXT.json
│   ├── VBusSpecificationResol-alle.xml  # Full spec (master)
│   ├── README.md
│   └── [other spec files]
│
├── captures/               # Storage for periodic raw captures (binary and parsed JSON)
│   ├── capture-2025-11-*.bin       # Raw binary VBUS data
│   ├── capture-2025-11-*.json      # Parsed JSON from captures
│   └── manifest.json               # Index of all captures
│
├── data/                   # SQLite database and WAL files
│   ├── resol_data.db      # Main SQLite database
│   ├── resol_data.db-shm  # Shared memory file (WAL mode)
│   └── resol_data.db-wal  # Write-ahead log
│
├── scripts/                # Utility scripts (e.g., installation helpers)
│
├── tests/
│   └── test_parse_capture.py  # Basic parsing tests
│
├── Testaufzeichnung/       # Historical test/sample capture data
│
├── README.md               # Original project README
├── SUMMARY.md              # High-level summary of architecture
├── SYSTEMD.md              # Instructions for collector systemd setup
└── LICENSE                 # Apache/MIT license

```

---

## Build, Test, and Run

### Prerequisites
- Python 3.x (Python 3 port from original Python 2)
- Virtual environment (recommended)

### Installation

```bash
# 1. Clone and enter directory
cd resol-vbus-python

# 2. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

### Core Usage Modes

#### 1. Parse Raw VBUS Data (One-Shot)
```bash
# From LAN device
python3 resol.py

# From serial port
python3 resol.py

# From captured binary file (stdin replay)
python3 resol.py < captures/capture-*.bin
```

#### 2. Continuous Collector Daemon
```bash
# Capture snapshots every 5 minutes and store in SQLite
python3 collector.py --interval 5 --db data/resol_data.db
```

#### 3. Periodic Capture to Files
```bash
# Capture 10 samples (300s total, 30s intervals) to captures/ directory
python3 capture_device.py --duration 300 --interval 30 --outdir captures
```

#### 4. Flask Web UI
```bash
# Run development server (accessible at http://<ip>:5000)
python3 ui/run_server.py

# Or directly:
python3 -m flask --app ui.app run --host 0.0.0.0 --port 5000
```

### Testing

```bash
# Run basic parser tests
python3 -m pytest tests/test_parse_capture.py -v

# Test database creation
python3 db.py  # Smoke test at module level
```

### Linting & Code Quality
No standard linting config found. Recommend adding:
- Black formatter
- Flake8 or ruff
- mypy for type checking

---

## High-Level Architecture

### Data Flow

```
RESOL Device (LAN/Serial) 
    ↓
[resol.py or collector.py]  ← Connects and reads raw VBUS bytes
    ↓
[parser.py]  ← Decodes septet-encoded frames, splits on 0xAA sync byte
    ↓
[spec.py]  ← Maps packets to device/field definitions from JSON spec
    ↓
[db.py]  ← Stores parsed snapshots in SQLite (snapshots table)
    ↓
[ui/app.py] ← Flask web UI reads from DB, displays current status
    ↓
Browser @ http://<pi-ip>:5000
```

### Main Components

#### 1. **VBUS Protocol Parsing** (`parser.py`, `resol.py`)
- **Frame Structure**: VBUS frames are septet-encoded (7 bits per 8-bit byte for space efficiency)
- **Sync Byte**: 0xAA marks frame boundaries; split on this byte to isolate messages
- **Message Header** (9 bytes):
  - Destination address (2 bytes)
  - Source address (2 bytes)
  - Protocol version (0x10=PV1, 0x20=PV2, 0x30=PV3)
  - Command (2 bytes)
  - Frame count (1 byte)
  - Checksum (1 byte)
- **Payload Frames**: Each frame is 6 bytes (4 data + septet + checksum)
  - `integrate_septett()` function reconstructs original 8-bit values from septet-encoded 7-bit values
- **Field Extraction** (`gb()` function): Interprets little-endian signed integers, applies scale factors and units

**Key Functions**:
- `parse_raw_bytes(raw: bytes) -> Dict` - Main entry point for parsing binary data
- `integrate_septett(frame: bytes) -> bytes` - Decodes 7-bit encoding
- `gb(data, begin, end) -> int` - Extract little-endian signed integers
- `get_source_name_from_msg()` - Map device address to human-readable name

#### 2. **Configuration** (`config.py`)
- `connection`: "lan", "serial", or "stdin"
- `address`: LAN IP and port (e.g., `("192.168.1.253", 7053)`)
- `vbus_pass`: VBUS device password for LAN auth
- `port`: Serial port path (e.g., `/dev/ttyACM0`)
- `baudrate`: Serial baud rate (typically 9600)
- `spec_file`: Path to JSON spec (e.g., `spec/DeltaSolSLL.json`)
- `expected_packets`: Number of unique packet types to wait for before completing
- `debug`: Verbose message parsing output

#### 3. **Specification Loading** (`spec.py`)
- Loads a JSON-converted RESOL spec file
- Structure:
  ```json
  {
    "vbusSpecification": {
      "device": [
        {"address": "0x2271", "mask": "0xffff", "name": "DeltaSol SLL [Regler]"},
        ...
      ],
      "packet": [
        {
          "source": "0x2271", "destination": "0x0010", "command": "0x0100",
          "field": [
            {"name": ["Temp. Sensor 1"], "offset": 0, "bitSize": 16, "factor": 0.1, "unit": "°C"},
            ...
          ]
        },
        ...
      ]
    }
  }
  ```

#### 4. **Database** (`db.py`)
- **Primary Table**: `snapshots` (JSON-based)
  - `id`, `ts` (ISO timestamp), `data` (JSON string of parsed snapshot)
- **Legacy Table**: `measurements` (normalized rows, kept for compatibility)
  - `id`, `ts`, `device`, `field`, `value`, `unit`
- **API**:
  - `DBManager.connect()` - Connect and create tables
  - `DBManager.insert_snapshot(ts, snapshot_dict)` - Insert parsed data as JSON
  - `DBManager._parse_value_and_unit(raw)` - Parse "23.4°C" → (23.4, "°C")

#### 5. **Collector Daemon** (`collector.py`)
- Runs in infinite loop, capturing snapshots at regular intervals
- For each iteration:
  1. Connect to device (LAN or serial)
  2. Read raw bytes for 2 seconds
  3. Parse using `parser.parse_raw_bytes()`
  4. Insert into SQLite via `db.insert_snapshot()`
  5. Sleep until next interval
- Can be run as a systemd service

#### 6. **Flask Web UI** (`ui/app.py`, `ui/run_server.py`)
- **Routes**:
  - `/` - Current status page (main view)
  - `/hour`, `/day`, `/week` - Placeholder routes (under construction)
- **Data Sources** (fallback chain):
  1. Latest row from SQLite `snapshots` table
  2. Cached snapshot from background `live_reader` thread (if running)
  3. Latest parsed capture JSON from `captures/` directory
- **Features**:
  - Sidebar navigation
  - Real-time or cached snapshot display
  - Data source badge (db, live, capture)
  - Data age computation ("5m ago", "2h 30m ago", etc.)
  - Customizable field mapping (hardcoded for DeltaSol SLL in `field_map`)

#### 7. **Live Reader Background Thread** (`ui/live_reader.py`)
- Starts on import (if running on Pi)
- Polls serial port every 5 seconds, reads 2 seconds of data
- Parses and caches latest snapshot in memory
- Used by Flask UI to avoid blocking requests
- Starts automatically when `app.py` is imported

---

## Important Patterns & Conventions

### 1. **Bytes Handling**
- All VBUS parsing uses Python 3 bytes objects
- Utility function `bytes_to_int(b)` normalizes int/bytes access
- `format_byte()` converts bytes to hex string format ("0xAB")

### 2. **Connection Abstraction**
- Multiple entry points accept "socket-like" objects with `recv()` or `read()` methods
- Serial, socket, and stdin connections use the same interface
- Allows offline testing by piping captured binary data via stdin

### 3. **Spec-Driven Field Mapping**
- Field extraction is fully driven by JSON spec files
- No hardcoded addresses or field offsets
- Easy to swap specs for different RESOL controller models

### 4. **Error Resilience**
- `parser.parse_raw_bytes()` tolerates malformed frames (catches exceptions)
- `collector.py` gracefully handles connection failures and continues polling
- UI falls back through multiple data sources if primary is unavailable

### 5. **Systemd Integration**
- Two service units provided:
  - `resol-collector.service` - Runs continuous collector daemon
  - `resol-ui.service` - Runs Flask web UI
- Uses ExecStart with explicit Python paths
- Can be enabled with `sudo systemctl enable resol-ui.service`

---

## Key Entry Points

1. **`resol.py`** - Main parser CLI; reads from device and prints JSON
2. **`collector.py`** - Collector daemon; saves snapshots to SQLite
3. **`capture_device.py`** - Periodic capture utility; writes `.bin` + `.json` files
4. **`ui/run_server.py`** - Flask UI launcher with LAN IP detection
5. **`parser.parse_raw_bytes()`** - Reusable parsing function for offline analysis

---

## Debugging Tips

### Enable Debug Mode
In `config.py`, set `debug = True`. This will:
- Print verbose protocol parsing (destination, source, command, frame count, etc.)
- Show payload details and checksum info
- Interleave with JSON output (so redirect carefully)

### Test Offline Parsing
```bash
# Parse a captured binary file
python3 resol.py < captures/capture-*.bin

# Or use the parser module directly
python3 -c "
import parser
with open('captures/capture-*.bin', 'rb') as f:
    raw = f.read()
    result = parser.parse_raw_bytes(raw)
    import json
    print(json.dumps(result, indent=2))
"
```

### Check Database Contents
```bash
sqlite3 data/resol_data.db
sqlite> SELECT COUNT(*) FROM snapshots;
sqlite> SELECT ts, LENGTH(data) FROM snapshots ORDER BY ts DESC LIMIT 5;
```

### Inspect Live Serial Feed
```bash
# On Raspberry Pi with connected serial device:
python3 -c "
from capture_device import connect_serial, read_for
sock = connect_serial()
raw = read_for(sock, seconds=5)
sock.close()
print(f'Read {len(raw)} bytes')
# or pipe to parser:
import parser
result = parser.parse_raw_bytes(raw)
import json
print(json.dumps(result, indent=2))
"
```

---

## Dependencies

- **Flask >= 2.0** - Web UI framework
- **pyserial >= 3.0** - Serial port communication
- **pytest >= 6.0** - Testing framework
- Python standard library: json, sqlite3, socket, sys, argparse, threading, time, datetime, re

---

## Current Branch & Development Status

- **Current branch**: `flask-ui` (active development branch)
- **Main branch**: `main` (stable releases)
- **Other branches**: `py3-port` (Python 3 migration work), `feature/json-snapshots-systemd`

### Recent Changes
- Added SQLite WAL mode files (`.db-shm`, `.db-wal`) for offline operation
- Integrated Flask UI with background live reader thread
- Data source badge on UI showing whether data is from DB, live, or capture
- Data age computation and display

---

## Common Development Tasks

### Add a New Route to Flask UI
Edit `ui/app.py`:
```python
@app.route('/path')
def route_name():
    snap = get_latest_snapshot()
    # process snapshot
    return render_template('template.html', data=snap)
```

### Change Field Mapping on Status Page
Edit the `field_map` list in `ui/app.py`:
```python
field_map = [
    ("Actual Field Name From Spec", "Display Label"),
    ...
]
```

### Use a Different Device Spec
Edit `config.py`:
```python
spec_file = 'spec/DeltaSolBX.json'  # or another model
```

### Run Collector as Systemd Service
1. Edit `systemd/resol-collector.service` (update paths and user)
2. `sudo cp systemd/resol-collector.service /etc/systemd/system/`
3. `sudo systemctl daemon-reload && sudo systemctl enable --now resol-collector.service`
4. Check with `sudo systemctl status resol-collector.service`

---

## Future Enhancements

- [ ] Add historical charts (hour, day, week views in UI)
- [ ] Add CI/CD workflow (GitHub Actions) to test on Python 3
- [ ] Add type hints for better IDE support
- [ ] Upgrade to WSGI server (Gunicorn) for production UI deployment
- [ ] Support for PV2/PV3 protocol parsing (currently only PV1 is fully decoded)
- [ ] Configuration UI to set connection parameters without editing config.py
- [ ] Email/alert support for threshold breaches (e.g., high collector temp)

---

## Notes for Claude

- This is a **data acquisition + visualization** project for a solar heating system
- The core parsing logic is mature and well-tested (septet decoding, spec-driven field extraction)
- Flask UI is newly added (active development on `flask-ui` branch)
- Background thread architecture allows responsive UI even with serial latency
- Designed for deployment on Raspberry Pi with minimal dependencies
- All connection types (LAN, serial, stdin) unified through socket-like interface
- No external databases or complex infrastructure required (SQLite only)

---

Generated: 2025-11-23
