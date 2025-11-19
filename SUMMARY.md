**Repository Summary**

- **Purpose**: Python script to read RESOL VBus data (from RESOL devices) over LAN, serial, or stdin, parse messages using RESOL spec files, and output JSON with parsed field values.

**Top-level Files**
- `resol.py`: Main entrypoint and parser — connects to device, reads raw VBUS frames, decodes them, maps packets to spec definitions, and prints a JSON result.
- `config.py`: Runtime configuration — choose connection type (`lan`, `serial`, `stdin`), network/serial settings, `spec_file` path, `expected_packets`, and `debug` flag.
- `spec.py`: Loads JSON-converted RESOL spec (from `config.spec_file`) and exposes `spec` variable used by `resol.py`.
- `README.md`: Usage notes and high-level instructions (mentions requirement for spec files and how to obtain/convert them).
- `spec/`: Directory with multiple JSON spec files (converted from RESOL XML). Example: `DeltaSolSLL.json` contains `device` and `packet` entries describing addresses, packet fields, offsets, bit sizes, scale factors and units.
- `Testaufzeichnung/`: Example/test capture files (images and JSON/text) — useful to inspect sample data.

**High-level flow**
- Load `config` and `spec`.
- Connect (LAN/serial/stdin) and read raw stream bytes until VBUS frames are found.
- Split stream on the sync byte (0xAA), decode septet-encoded frames, and extract payloads.
- Map messages (`source`, `destination`, `command`) to `packet` entries in the spec, then extract fields by offset/bitSize and apply `factor` and `unit`.
- Output a JSON dictionary keyed by source device name with field name → value strings.

**Important functions**
- `login()` — LAN handshake (HELLO/PASS/OK).
- `load_data()` — read/parse loop until `expected_packets` collected.
- `integrate_septett()` — decodes septet-encoded frames into bytes.
- `gb()` — interprets little-endian signed integers from byte ranges.
- `parse_payload()` — maps payload bytes to spec fields and populates the result.

**Notes & Recommendations**
- The code was ported to Python 3 and now uses bytes-aware helpers; `pyserial` is still required for serial connections.
- Consider adding tests that replay captures from `Testaufzeichnung` via `stdin` mode.
- Add a `requirements.txt` and CI for Python 3 testing.

Generated on 2025-11-19 by repository audit.
