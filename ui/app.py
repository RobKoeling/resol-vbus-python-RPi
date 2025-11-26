#!/usr/bin/env python3
"""Minimal Flask UI for resol-vbus-python.

Provides a left-hand sidebar with navigation and a status panel showing
the current device snapshot (latest snapshot from the `snapshots` table).
"""

from flask import Flask, render_template, url_for, jsonify, request
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

# Load the tap temperature predictor
try:
    spec_pred = importlib.util.spec_from_file_location('ui_predictor', str(Path(__file__).parent / 'predictor.py'))
    ui_predictor = importlib.util.module_from_spec(spec_pred)
    spec_pred.loader.exec_module(ui_predictor)
except Exception:
    ui_predictor = None

static_folder_path = str((Path(__file__).parent / 'static').resolve())
template_folder_path = str((Path(__file__).parent / 'templates').resolve())

app = Flask(__name__, static_url_path='/static', static_folder=static_folder_path,
            template_folder=template_folder_path)


def get_db_status(db_path=None):
    """Get database status info: latest entry, snapshot count, daemon health."""
    try:
        manager = db.DBManager(path=db_path) if db_path else db.DBManager()
        manager.connect()
        cur = manager.conn.cursor()

        # Get latest snapshot timestamp
        cur.execute('SELECT ts FROM snapshots ORDER BY ts DESC LIMIT 1')
        row = cur.fetchone()
        latest_ts = row[0] if row else None

        # Get count of snapshots in last hour (to check daemon activity)
        # Note: ts is ISO format (2025-11-23T11:46:44Z), convert for comparison
        cur.execute('''
            SELECT COUNT(*) FROM snapshots
            WHERE datetime(replace(replace(ts, 'T', ' '), 'Z', '')) >= datetime('now', '-1 hour')
        ''')
        count_last_hour = cur.fetchone()[0]

        # Get total snapshot count
        cur.execute('SELECT COUNT(*) FROM snapshots')
        total_count = cur.fetchone()[0]

        # Get count of snapshots in last 5 minutes (daemon health check)
        cur.execute('''
            SELECT COUNT(*) FROM snapshots
            WHERE datetime(replace(replace(ts, 'T', ' '), 'Z', '')) >= datetime('now', '-5 minutes')
        ''')
        count_last_5min = cur.fetchone()[0]

        # Get earliest snapshot timestamp (data collection start date)
        cur.execute('SELECT ts FROM snapshots ORDER BY ts ASC LIMIT 1')
        row = cur.fetchone()
        earliest_ts = row[0] if row else None

        # Get database file size
        import os
        db_path = manager.path
        db_size_bytes = os.path.getsize(db_path) if os.path.exists(db_path) else 0
        db_size_mb = round(db_size_bytes / (1024 * 1024), 2)

        # Determine daemon status
        if count_last_5min > 0:
            daemon_status = 'active'
        elif count_last_hour > 0:
            daemon_status = 'stale'
        else:
            daemon_status = 'inactive'

        return {
            'latest_ts': latest_ts,
            'latest_age': _format_age(latest_ts) if latest_ts else None,
            'earliest_ts': earliest_ts,
            'count_last_hour': count_last_hour,
            'count_last_5min': count_last_5min,
            'total_count': total_count,
            'db_size_mb': db_size_mb,
            'daemon_status': daemon_status,
            'db_connected': True
        }
    except Exception as e:
        return {
            'latest_ts': None,
            'latest_age': None,
            'earliest_ts': None,
            'count_last_hour': 0,
            'count_last_5min': 0,
            'total_count': 0,
            'db_size_mb': 0,
            'daemon_status': 'error',
            'db_connected': False,
            'error': str(e)
        }


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
            return {'ts': ts, 'data': data, 'source': 'db'}
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
            return {'ts': datetime.utcnow().isoformat() + 'Z', 'data': parsed, 'source': 'live'}
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
                    return {'ts': last.get('timestamp'), 'data': data, 'source': 'capture'}
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
        return {'ts': ts, 'data': data, 'source': 'capture'}
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

    # determine data source and age
    source = None
    age = None
    if snap and isinstance(snap, dict):
        source = snap.get('source')
        ts = snap.get('ts')
        age = _format_age(ts)

    # Get database status
    db_status = get_db_status()

    return render_template('status.html', device_name=device_name, now=datetime.now(), status_fields=status_fields, data_source=source, data_age=age, db_status=db_status)


def _format_age(ts_str):
    """Return a human readable age string like '5s ago', '3m ago', '2h 5m ago'.

    Accepts ISO timestamps (with trailing 'Z') and also the capture filename
    style timestamps (`2025-11-19T12-00-00Z`). Returns None on parse failure.
    """
    if not ts_str:
        return None
    from datetime import datetime
    import re

    s = str(ts_str)
    # normalize common variants: trailing Z -> +00:00 for fromisoformat
    try:
        if s.endswith('Z'):
            dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
        else:
            # try to fix time separators if filename-style (T12-00-00)
            m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)", s)
            if m:
                fixed = re.sub(r"T(\d{2})-(\d{2})-(\d{2})Z", r"T\1:\2:\3+00:00", s)
                dt = datetime.fromisoformat(fixed)
            else:
                dt = datetime.fromisoformat(s)
    except Exception:
        try:
            # last resort: strip non-digits and give up
            return None
        except Exception:
            return None

    now = datetime.utcnow().replace(tzinfo=dt.tzinfo) if dt.tzinfo else datetime.utcnow()
    # ensure both naive or both aware: compare in UTC naive
    try:
        delta = now - dt.replace(tzinfo=None)
    except Exception:
        delta = now - dt

    secs = int(delta.total_seconds())
    if secs < 0:
        return 'just now'
    if secs < 60:
        return f"{secs}s ago"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m ago"
    hours = mins // 60
    if hours < 24:
        rem = mins % 60
        return f"{hours}h {rem}m ago" if rem else f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


# Mapping of period names to SQLite interval strings
PERIOD_INTERVALS = {
    'hour': '-1 hour',
    'day': '-1 day',
    'week': '-7 days',
    'month': '-30 days',
}


def _parse_iso_timestamp(ts_str):
    """Parse ISO timestamp string to datetime object."""
    try:
        # Handle ISO format with Z suffix
        s = ts_str.replace('Z', '+00:00')
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _get_expected_interval_minutes(cur):
    """Determine expected interval between readings by analyzing last 100 entries.

    Returns the median gap in minutes, or 5.0 as default if insufficient data.
    """
    cur.execute('SELECT ts FROM snapshots ORDER BY ts DESC LIMIT 100')
    rows = cur.fetchall()

    if len(rows) < 2:
        return 5.0  # Default to 5 minutes if not enough data

    # Parse timestamps and calculate gaps
    timestamps = []
    for (ts,) in rows:
        dt = _parse_iso_timestamp(ts)
        if dt:
            timestamps.append(dt)

    if len(timestamps) < 2:
        return 5.0

    # Calculate gaps between consecutive readings (timestamps are DESC, so reverse)
    timestamps.reverse()
    gaps = []
    for i in range(1, len(timestamps)):
        gap = (timestamps[i] - timestamps[i-1]).total_seconds() / 60
        if gap > 0:
            gaps.append(gap)

    if not gaps:
        return 5.0

    # Return median gap
    gaps.sort()
    median_idx = len(gaps) // 2
    return gaps[median_idx]


def get_history_data(period='hour', db_path=None):
    """Fetch snapshots for the given period and extract temperature + pump data.

    Args:
        period: One of 'hour', 'day', 'week'
        db_path: Optional database path override

    Gaps in data (> 2x expected interval) are represented by null values
    so Chart.js will break the line instead of connecting across gaps.
    """
    interval = PERIOD_INTERVALS.get(period, '-1 hour')

    try:
        manager = db.DBManager(path=db_path) if db_path else db.DBManager()
        manager.connect()
        cur = manager.conn.cursor()

        # Determine gap threshold dynamically (2x the expected interval)
        expected_interval = _get_expected_interval_minutes(cur)
        gap_threshold = expected_interval * 2

        # Get snapshots for the specified period
        # Note: ts is ISO format (2025-11-23T11:46:44Z), convert for comparison
        cur.execute(f'''
            SELECT ts, data FROM snapshots
            WHERE datetime(replace(replace(ts, 'T', ' '), 'Z', '')) >= datetime('now', '{interval}')
            ORDER BY ts ASC
        ''')
        rows = cur.fetchall()

        timestamps = []
        temp1 = []
        temp2 = []
        temp3 = []
        pump1 = []

        prev_dt = None

        for ts, data_text in rows:
            try:
                data = json.loads(data_text)
            except Exception:
                continue

            # Get the first device's data
            if not data:
                continue
            device_data = list(data.values())[0] if isinstance(data, dict) else {}

            # Check for gap from previous reading
            curr_dt = _parse_iso_timestamp(ts)
            if prev_dt and curr_dt:
                gap_minutes = (curr_dt - prev_dt).total_seconds() / 60
                if gap_minutes > gap_threshold:
                    # Insert null entry to break the line in the chart
                    timestamps.append(None)
                    temp1.append(None)
                    temp2.append(None)
                    temp3.append(None)
                    pump1.append(None)

            prev_dt = curr_dt
            timestamps.append(ts)

            # Extract temperature values
            for field_name, target_list in [
                ("Temp. Sensor 1", temp1),
                ("Temp. Sensor 2", temp2),
                ("Temp. Sensor 3", temp3),
                ("Pump Speed Relay 1", pump1),
            ]:
                raw = device_data.get(field_name)
                val, _ = db.DBManager._parse_value_and_unit(raw)
                target_list.append(val if val is not None else None)

        return {
            'timestamps': timestamps,
            'temp1': temp1,
            'temp2': temp2,
            'temp3': temp3,
            'pump1': pump1
        }
    except Exception as e:
        return {'error': str(e), 'timestamps': [], 'temp1': [], 'temp2': [], 'temp3': [], 'pump1': []}


# Mapping of period names to display titles
PERIOD_TITLES = {
    'hour': 'Last Hour',
    'day': 'Last 24 Hours',
    'week': 'Last 7 Days',
    'month': 'Last 30 Days',
}


@app.route('/api/history/<period>')
def api_history(period):
    """API endpoint returning temperature and pump data for the specified period."""
    if period not in PERIOD_INTERVALS:
        return jsonify({'error': f'Invalid period: {period}. Use: hour, day, week, month'}), 400
    data = get_history_data(period)
    return jsonify(data)


@app.route('/api/tap-reading', methods=['POST'])
def api_tap_reading():
    """Submit a manual tap temperature reading.

    Expects JSON: {"tap_temp": <float>}
    Takes a fresh reading from the serial port for accurate tank temperatures.
    """
    try:
        data = request.get_json()
        if not data or 'tap_temp' not in data:
            return jsonify({'error': 'Missing tap_temp in request body'}), 400

        tap_temp = float(data['tap_temp'])
        if tap_temp < 0 or tap_temp > 100:
            return jsonify({'error': 'tap_temp must be between 0 and 100'}), 400

        # Get fresh tank readings from serial port (not from potentially stale DB)
        snap = get_live_snapshot_from_serial(read_seconds=3.0)
        if snap is None:
            return jsonify({'error': 'Could not read from serial port. Is the device connected?'}), 500

        device_data = {}
        if snap and snap.get('data'):
            data_dict = snap['data']
            if isinstance(data_dict, dict) and len(data_dict) > 0:
                device_data = list(data_dict.values())[0]

        tank_lower_raw = device_data.get('Temp. Sensor 2')
        tank_upper_raw = device_data.get('Temp. Sensor 3')

        tank_lower, _ = db.DBManager._parse_value_and_unit(tank_lower_raw)
        tank_upper, _ = db.DBManager._parse_value_and_unit(tank_upper_raw)

        if tank_lower is None or tank_upper is None:
            return jsonify({'error': 'Could not parse tank temperatures from serial reading'}), 500

        # Get the current prediction before storing (if model is trained)
        predicted_temp = None
        if ui_predictor:
            predictor = ui_predictor.get_predictor()
            predicted_temp = predictor.predict(tank_lower, tank_upper)

        # Store the reading with the prediction
        ts = datetime.utcnow().isoformat() + 'Z'
        manager = db.DBManager()
        manager.connect()
        manager.insert_tap_reading(ts, tap_temp, tank_lower, tank_upper, predicted_temp)

        # Retrain the predictor with new data
        if ui_predictor:
            ui_predictor.retrain_predictor()

        return jsonify({
            'success': True,
            'reading': {
                'ts': ts,
                'tap_temp': tap_temp,
                'tank_lower': tank_lower,
                'tank_upper': tank_upper,
                'predicted_temp': round(predicted_temp, 1) if predicted_temp is not None else None
            }
        })
    except ValueError as e:
        return jsonify({'error': f'Invalid tap_temp value: {e}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tap-readings')
def api_tap_readings():
    """Get recent tap temperature readings."""
    try:
        limit = request.args.get('limit', 20, type=int)
        manager = db.DBManager()
        manager.connect()
        readings = manager.get_tap_readings(limit=limit)
        count = manager.get_tap_readings_count()
        return jsonify({'readings': readings, 'total_count': count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tap-prediction')
def api_tap_prediction():
    """Get predicted tap temperature based on current tank readings."""
    try:
        if ui_predictor is None:
            return jsonify({'error': 'Predictor module not loaded'}), 500

        predictor = ui_predictor.get_predictor()

        # Get current tank readings
        snap = get_latest_snapshot()
        if snap is None:
            return jsonify({'error': 'No snapshot available'}), 500

        device_data = {}
        if snap and snap.get('data'):
            data_dict = snap['data']
            if isinstance(data_dict, dict) and len(data_dict) > 0:
                device_data = list(data_dict.values())[0]

        tank_lower_raw = device_data.get('Temp. Sensor 2')
        tank_upper_raw = device_data.get('Temp. Sensor 3')

        tank_lower, _ = db.DBManager._parse_value_and_unit(tank_lower_raw)
        tank_upper, _ = db.DBManager._parse_value_and_unit(tank_upper_raw)

        prediction = None
        if tank_lower is not None and tank_upper is not None:
            prediction = predictor.predict(tank_lower, tank_upper)

        stats = predictor.get_stats()

        return jsonify({
            'prediction': round(prediction, 1) if prediction is not None else None,
            'tank_lower': tank_lower,
            'tank_upper': tank_upper,
            'model_stats': stats
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/hour')
def hour():
    """Render the Last Hour graph page."""
    return render_template('history.html', period='hour', title=PERIOD_TITLES['hour'], now=datetime.now())


@app.route('/day')
def day():
    """Render the Last 24 Hours graph page."""
    return render_template('history.html', period='day', title=PERIOD_TITLES['day'], now=datetime.now())


@app.route('/week')
def week():
    """Render the Last 7 Days graph page."""
    return render_template('history.html', period='week', title=PERIOD_TITLES['week'], now=datetime.now())


@app.route('/month')
def month():
    """Render the Last 30 Days graph page."""
    return render_template('history.html', period='month', title=PERIOD_TITLES['month'], now=datetime.now())


def get_comfort_level(temp):
    """Calculate shower comfort level based on predicted tap temperature.

    Args:
        temp: Predicted temperature in Celsius

    Returns:
        Tuple of (comfort_level, color) where comfort_level is one of:
        'Hot', 'Comfortable', 'Luke Warm', 'Cold'
    """
    if temp is None:
        return 'Unknown', '#6b7280'  # gray
    if temp >= 50:
        return 'Hot', '#ef4444'  # red
    elif temp >= 40:
        return 'Comfortable', '#22c55e'  # green
    elif temp >= 30:
        return 'Luke Warm', '#f59e0b'  # orange
    else:
        return 'Cold', '#3b82f6'  # blue


@app.route('/shower')
def shower():
    """Render the shower comfort prediction page (mobile-only feature)."""
    predicted_temp = None
    comfort_level = 'Unknown'
    color = '#6b7280'
    error_message = None

    if ui_predictor is None:
        error_message = 'Predictor not available'
    else:
        try:
            predictor = ui_predictor.get_predictor()
            # Get latest snapshot for current tank temperatures
            snapshot = get_latest_snapshot()
            if snapshot and 'parsed' in snapshot:
                data = snapshot['parsed']
                device_data = data.get('DeltaSol MX [Regler]', {})

                tank_lower_raw = device_data.get('Temperature Sensor 2')
                tank_upper_raw = device_data.get('Temperature Sensor 3')

                tank_lower, _ = DBManager._parse_value_and_unit(tank_lower_raw)
                tank_upper, _ = DBManager._parse_value_and_unit(tank_upper_raw)

                if tank_lower is not None and tank_upper is not None:
                    predicted_temp = predictor.predict(tank_lower, tank_upper)
                    comfort_level, color = get_comfort_level(predicted_temp)
                else:
                    error_message = 'Tank temperature sensors not available'
            else:
                error_message = 'No data available'
        except Exception as e:
            error_message = f'Prediction error: {str(e)}'

    return render_template('shower.html',
                         predicted_temp=predicted_temp,
                         comfort_level=comfort_level,
                         color=color,
                         error_message=error_message,
                         now=datetime.now())


@app.route('/api/shower-feedback', methods=['POST'])
def api_shower_feedback():
    """Store user feedback on shower comfort prediction."""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    predicted_temp = data.get('predicted_temp')
    comfort_level = data.get('comfort_level')
    feedback = data.get('feedback')  # 'thumbs_up' or 'thumbs_down'

    if not all([predicted_temp is not None, comfort_level, feedback]):
        return jsonify({'error': 'Missing required fields'}), 400

    if feedback not in ['thumbs_up', 'thumbs_down']:
        return jsonify({'error': 'Invalid feedback value'}), 400

    ts = datetime.utcnow().isoformat() + 'Z'

    try:
        manager.insert_shower_feedback(ts, predicted_temp, comfort_level, feedback)
        return jsonify({'success': True, 'message': 'Feedback recorded'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # Run development server for quick testing (listen on all interfaces so other hosts can connect)
    app.run(host='0.0.0.0', port=5000, debug=True)
