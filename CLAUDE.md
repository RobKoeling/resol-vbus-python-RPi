# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python application for reading RESOL VBUS protocol data from solar heating systems. Parses VBUS frames from DeltaSol controllers (via LAN, serial, or stdin), stores data in SQLite, and displays via Flask web UI.

## Common Commands

```bash
# Install dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run parser (one-shot JSON output)
python3 resol.py                    # from configured LAN/serial
python3 resol.py < captures/*.bin   # replay captured file

# Run collector daemon (periodic snapshots to SQLite)
python3 collector.py --interval 5 --db data/resol_data.db

# Run Flask web UI
python3 ui/run_server.py            # with LAN IP detection
python3 -m flask --app ui.app run --host 0.0.0.0 --port 5000

# Run tests
python3 -m pytest tests/test_parse_capture.py -v

# Check database
sqlite3 data/resol_data.db "SELECT ts, LENGTH(data) FROM snapshots ORDER BY ts DESC LIMIT 5;"
```

## Architecture

```
RESOL Device (LAN/Serial) → resol.py/collector.py → parser.py → spec.py → db.py → ui/app.py → Browser
```

### Key Modules

- **`parser.py`** - Core VBUS parsing: septet decoding, frame splitting on 0xAA sync byte, field extraction via `parse_raw_bytes(raw: bytes) -> Dict`
- **`config.py`** - Runtime config: `connection` (lan/serial/stdin), `address`, `port`, `spec_file`, `debug`
- **`spec.py`** - Loads JSON spec files from `spec/` directory mapping device addresses to field definitions
- **`db.py`** - SQLite manager with `snapshots` table (JSON blobs) and `measurements` table (normalized rows)
- **`collector.py`** - Daemon that captures snapshots at intervals and stores in SQLite
- **`ui/app.py`** - Flask routes; data sources: SQLite → live_reader cache → captures/ directory (fallback chain)
- **`ui/live_reader.py`** - Background thread polling serial port, caches latest snapshot

### VBUS Protocol

- Frames are septet-encoded (7 bits per byte)
- 0xAA is sync byte marking frame boundaries
- `integrate_septett()` reconstructs 8-bit values
- `gb(data, begin, end)` extracts little-endian signed integers
- Field interpretation driven by JSON spec files (offset, bitSize, factor, unit)

## Configuration

Edit `config.py`:
- `connection`: "lan", "serial", or "stdin"
- `address`: LAN IP tuple, e.g., `("192.168.1.253", 7053)`
- `port`: Serial device, e.g., `/dev/ttyACM0`
- `spec_file`: Path to JSON spec, e.g., `spec/DeltaSolSLL.json`
- `debug`: Enable verbose parsing output

## Deployment

Systemd service templates in `systemd/`:
- `resol-collector.service` - Collector daemon
- `resol-ui.service` - Flask web UI

Target platform: Raspberry Pi with serial connection to RESOL device.
