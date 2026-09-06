resol-vbus-python
=================

Python script to read RESOL VBUS data over LAN, serial, or stdin and output parsed fields as JSON.

Overview
--------

This repository contains a small parser that connects to a RESOL VBUS device (via LAN or serial), reads VBUS frames, decodes the septet-encoded payloads, maps packets to a RESOL spec file, and prints a JSON dictionary of parsed field values keyed by device name.

Quickstart (Python 3)
---------------------

1. Install dependencies (recommended inside a virtual environment):

```bash
python3 -m pip install -r requirements.txt
```

2. Configure `config.py`:

- Set `connection` to one of: `"lan"`, `"serial"`, or `"stdin"`.
- For LAN: set `address = ("<IP>", <port>)` and `vbus_pass`.
- For serial: set `port` and `baudrate`.
- Set `spec_file` to a JSON spec (in `spec/` or a converted RESOL RSC file).
- Adjust `expected_packets` (how many unique source packets to wait for) and `debug` as needed.

3. Run the parser:

```bash
python3 resol.py
```

If you want to replay a raw capture file via stdin:

```bash
python3 resol.py < capture.bin
```

Example output
--------------

The script prints a JSON object (one-shot) with device names as keys and field name → value strings as values. Example:

```json
{
    "DeltaSol SLL [Regler]": {
        "Temp. Sensor 1": "23.4°C",
        "Temp. Sensor 2": "19.8°C",
        "Pump 1": "75%"
    }
}
```

Spec files
----------

Spec files are JSON-converted versions of the RESOL RSC XML specification files (included in `spec/`). You can convert the original XML using an XML→JSON converter, or obtain the JSON specs from a compatible source. Each spec contains `device` and `packet` definitions used by the parser.

Debugging
---------

- Set `debug = True` in `config.py` to get verbose message parsing output. Note: enabling debug will interleave textual debug output with any JSON printed by the script.

Notes & Next Steps
------------------

- This repository was ported to Python 3 (see branch `py3-port`). Values are currently emitted as strings with units appended. If you prefer structured numeric output (separate `value` and `unit` fields), I can update the output format.
- Consider adding tests that replay captures from `Testaufzeichnung/` and a CI workflow to validate the parser on Python 3.

Raspberry Pi access
--------------------

The collector/UI normally run on a Raspberry Pi on the local network:

- IP address: `192.168.178.28` (DHCP-assigned; may change if not reserved on the router)
- SSH: `ssh rob@192.168.178.28`
- Web UI: `http://192.168.178.28:5000/`

If the IP has changed, scan the local subnet to rediscover it, e.g. `nmap -Pn -p 22 --open 192.168.178.0/24`.
