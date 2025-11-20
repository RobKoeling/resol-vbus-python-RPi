#!/usr/bin/env python3
"""Minimal Flask UI for resol-vbus-python.

Provides a left-hand sidebar with navigation and a status panel showing
the current device snapshot (latest snapshot from the `snapshots` table).
"""

from flask import Flask, render_template, url_for
from pathlib import Path
import json
from datetime import datetime

import db
import importlib.util

# Try to load the background live reader from `ui/live_reader.py` so it
# begins polling when the app is imported. We use importlib to avoid
# requiring `ui` to be a package.
try:
    spec_lr = importlib.util.spec_from_file_location('ui_live_reader', str(Path(__file__).parent / 'live_reader.py'))
    ui_live_reader = importlib.util.module_from_spec(spec_lr)
    spec_lr.loader.exec_module(ui_live_reader)
except Exception:
    ui_live_reader = None

static_folder_path = str((Path(__file__).parent / 'static').resolve())
template_folder_path = str((Path(__file__).parent / 'templates').resolve())

app = Flask(__name__, static_url_path='/static', static_folder=static_folder_path,
            template_folder=template_folder_path)


def get_latest_snapshot(db_path=None):
    # Try to read from the SQLite snapshots table first. If the DB is not
    # present or empty (for example when running on the laptop), fall back
    # to any parsed capture JSON files saved under `captures/`.
    try:
        manager = db.DBManager(path=db_path) if db_path else db.DBManager()
        manager.connect()
        cur = manager.conn.cursor()
        cur.execute('SELECT ts, data FROM snapshots ORDER BY ts DESC, id DESC LIMIT 1')
        row = cur.fetchone()
        if row:
            ts, data_text = row[0], row[1]
            try:
                data = json.loads(data_text)
            except Exception:
                data = {}
            return {'ts': ts, 'data': data}
    except Exception:
        # DB not available or error reading it; fall through to captures
        pass

    # Before falling back to captures, if a background live reader is
    # available use its cached snapshot. This avoids blocking the request
    # while performing a live serial read.
    try:
        if ui_live_reader is not None:
            cached = ui_live_reader.get_cached_snapshot()
            if cached:
                return cached
    except Exception:
        # ignore and continue to captures fallback
        pass

    # Fallback: look for latest parsed capture JSON in `captures/`
    cap = get_latest_from_captures()
    return cap


def get_live_snapshot_from_serial(read_seconds=2.0):
    """Attempt to open the configured serial port, read a short sample
    and parse it. Returns {'ts': ..., 'data': {...}} or None on failure.
    """
    try:
        # reuse helpers from capture_device and parser to avoid duplicating
        # parsing logic.
        from capture_device import connect_serial, read_for
        import parser as _parser
        from datetime import datetime

        sock = connect_serial()
        try:
            raw = read_for(sock, seconds=read_seconds)
        finally:
            try:
                sock.close()
            except Exception:
                pass

        if not raw:
            return None

        try:
            parsed = _parser.parse_raw_bytes(raw)
        except Exception:
            parsed = None

        if parsed:
            return {'ts': datetime.utcnow().isoformat() + 'Z', 'data': parsed}
    except Exception:
        return None


def get_latest_from_captures(outdir='captures'):
    """Return the latest parsed capture as {'ts': ..., 'data': {...}} or None.

    The capture process writes <outdir>/manifest.json listing captures and
    also writes a `.json` file next to each `.bin` capture containing the
    parsed snapshot. This helper prefers the manifest but will also scan for
    the newest JSON file.
    """
    import os

    manifest = os.path.join(outdir, 'manifest.json')
    if os.path.exists(manifest):
        try:
            with open(manifest, 'r', encoding='utf-8') as mf:
                m = json.load(mf)
            samples = m.get('samples', [])
            if samples:
                # manifest samples have keys 'json' and 'timestamp'
                last = samples[-1]
                jsonfile = os.path.join(outdir, last.get('json', ''))
                if os.path.exists(jsonfile):
                    with open(jsonfile, 'r', encoding='utf-8') as jf:
                        data = json.load(jf)
                    return {'ts': last.get('timestamp'), 'data': data}
        except Exception:
            pass

    # No manifest or failed to read: scan directory for newest .json file
    try:
        files = []
        for fn in os.listdir(outdir) if os.path.isdir(outdir) else []:
            if fn.lower().endswith('.json'):
                files.append(os.path.join(outdir, fn))
        if not files:
            return None
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        newest = files[0]
        with open(newest, 'r', encoding='utf-8') as jf:
            data = json.load(jf)
        # try to derive timestamp from filename if available
        ts = None
        try:
            ts = os.path.basename(newest).split('.json')[0].replace('capture-', '')
        except Exception:
            ts = None
        return {'ts': ts, 'data': data}
    except Exception:
        return None


@app.route('/')
def index():
    snap = get_latest_snapshot()
    if snap is None:
        device_name = None
        device_fields = {}
    else:
        # pick the first device in the snapshot
        data = snap['data']
        if isinstance(data, dict) and len(data) > 0:
            device_name = list(data.keys())[0]
            device_fields = data.get(device_name, {}) or {}
        else:
            device_name = None
            device_fields = {}

    # Desired field names and their display labels
    field_map = [
        ("Temp. Sensor 1", "Solar Panel"),
        ("Temp. Sensor 2", "Tank (Lower)"),
        ("Temp. Sensor 3", "Tank (Upper)"),
        ("Pump Speed Relay 1", "Pump Activation"),
    ]

    # helper to parse numeric value
    def render_field(raw, is_temp=False):
        if raw is None:
            return 'N/A'
        # try parse using DB helper
        val, unit = db.DBManager._parse_value_and_unit(raw)
        if val is None:
            # fallback to raw string
            return str(raw)
        if is_temp:
            return f"{val:.1f}°C"
        # generic formatting: show unit if present
        if unit:
            return f"{val} {unit}"
        return str(val)

    status_fields = []
    for fname, label in field_map:
        raw = device_fields.get(fname)
        is_temp = fname.startswith('Temp')
        status_fields.append({'label': label, 'value': render_field(raw, is_temp)})

    return render_template('status.html', device_name=device_name, now=datetime.now(), status_fields=status_fields)


@app.route('/hour')
@app.route('/day')
@app.route('/week')
def under_construction():
    return render_template('status.html', device_name=None, now=datetime.now(), status_fields=[], message='Under Construction')


if __name__ == '__main__':
    # Run development server for quick testing (listen on all interfaces so other hosts can connect)
    app.run(host='0.0.0.0', port=5000, debug=True)
