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

app = Flask(__name__, static_url_path='/static', static_folder=str(Path(__file__).parent / 'static'))


def get_latest_snapshot(db_path=None):
    manager = db.DBManager(path=db_path) if db_path else db.DBManager()
    manager.connect()
    cur = manager.conn.cursor()
    cur.execute('SELECT ts, data FROM snapshots ORDER BY ts DESC, id DESC LIMIT 1')
    row = cur.fetchone()
    if not row:
        return None
    ts, data_text = row[0], row[1]
    try:
        data = json.loads(data_text)
    except Exception:
        data = {}
    return {'ts': ts, 'data': data}


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
