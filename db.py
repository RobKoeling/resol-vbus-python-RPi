#!/usr/bin/env python3
"""Simple SQLite DB manager for storing snapshots of parsed VBUS data.

Schema:
- measurements(id INTEGER PRIMARY KEY, ts TEXT, device TEXT, field TEXT, value REAL, unit TEXT)

Provides a small API for inserting snapshots atomically.
"""

import sqlite3
from typing import Dict


class DBManager:
    def __init__(self, path: str = 'data/resol_data.db'):
        self.path = path
        self.conn = None

    def connect(self):
        # Ensure directory exists
        import os
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        self.conn.execute('PRAGMA journal_mode=WAL')
        self._create_tables()

    def _create_tables(self):
        cur = self.conn.cursor()
        # legacy normalized table (kept for compatibility)
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                device TEXT NOT NULL,
                field TEXT NOT NULL,
                value REAL,
                unit TEXT
            )
            '''
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_measurements_ts ON measurements(ts)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_measurements_device_field ON measurements(device, field)')

        # preferred snapshots table: stores the full parsed snapshot as JSON
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                data TEXT NOT NULL -- JSON text of { device: { field: "value unit", ... }, ... }
            )
            '''
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts)')

        # tap_readings table: stores manual tap temperature readings for prediction model
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS tap_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                tap_temp REAL NOT NULL,
                tank_lower REAL,
                tank_upper REAL,
                predicted_temp REAL
            )
            '''
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_tap_readings_ts ON tap_readings(ts)')

        # Add predicted_temp column if it doesn't exist (for existing databases)
        try:
            cur.execute('ALTER TABLE tap_readings ADD COLUMN predicted_temp REAL')
        except sqlite3.OperationalError:
            pass  # Column already exists

        # shower_feedback table: stores user feedback on shower comfort predictions
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS shower_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                predicted_temp REAL,
                comfort_level TEXT,
                feedback TEXT
            )
            '''
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_shower_feedback_ts ON shower_feedback(ts)')
        self.conn.commit()

    def insert_snapshot(self, ts: str, snapshot: Dict[str, Dict[str, str]]):
        """Insert a snapshot as structured JSON into the `snapshots` table.

        This is the preferred storage method: the entire parsed snapshot is saved
        as JSON in one row (timestamp + data). The legacy `measurements` table is
        kept for backwards compatibility but not written by default.
        """
        if self.conn is None:
            self.connect()

        cur = self.conn.cursor()
        import json as _json
        json_text = _json.dumps(snapshot, ensure_ascii=False)
        cur.execute('INSERT INTO snapshots (ts, data) VALUES (?, ?)', (ts, json_text))
        self.conn.commit()

    def insert_snapshot_rows(self, ts: str, snapshot: Dict[str, Dict[str, str]]):
        """(Compatibility helper) Insert snapshot as normalized rows into `measurements`.

        Use this only if you need the old row format.
        """
        if self.conn is None:
            self.connect()

        cur = self.conn.cursor()
        rows = []
        for device, fields in snapshot.items():
            for field_name, raw_value in fields.items():
                # try to split numeric value and unit
                value, unit = self._parse_value_and_unit(raw_value)
                rows.append((ts, device, field_name, value, unit))

        if rows:
            cur.executemany('INSERT INTO measurements (ts, device, field, value, unit) VALUES (?,?,?,?,?)', rows)
            self.conn.commit()

    def insert_tap_reading(self, ts: str, tap_temp: float, tank_lower: float, tank_upper: float, predicted_temp: float = None):
        """Insert a manual tap temperature reading with corresponding tank sensor values and prediction."""
        if self.conn is None:
            self.connect()

        cur = self.conn.cursor()
        cur.execute(
            'INSERT INTO tap_readings (ts, tap_temp, tank_lower, tank_upper, predicted_temp) VALUES (?, ?, ?, ?, ?)',
            (ts, tap_temp, tank_lower, tank_upper, predicted_temp)
        )
        self.conn.commit()

    def get_tap_readings(self, limit: int = None):
        """Retrieve tap readings for training the prediction model.

        Returns list of dicts with keys: ts, tap_temp, tank_lower, tank_upper, predicted_temp
        """
        if self.conn is None:
            self.connect()

        cur = self.conn.cursor()
        if limit:
            cur.execute(
                'SELECT ts, tap_temp, tank_lower, tank_upper, predicted_temp FROM tap_readings ORDER BY ts DESC LIMIT ?',
                (limit,)
            )
        else:
            cur.execute('SELECT ts, tap_temp, tank_lower, tank_upper, predicted_temp FROM tap_readings ORDER BY ts DESC')

        rows = cur.fetchall()
        return [
            {'ts': r[0], 'tap_temp': r[1], 'tank_lower': r[2], 'tank_upper': r[3], 'predicted_temp': r[4]}
            for r in rows
        ]

    def get_tap_readings_count(self):
        """Return the total number of tap readings stored."""
        if self.conn is None:
            self.connect()

        cur = self.conn.cursor()
        cur.execute('SELECT COUNT(*) FROM tap_readings')
        return cur.fetchone()[0]

    def insert_shower_feedback(self, ts: str, predicted_temp: float, comfort_level: str, feedback: str):
        """Insert user feedback on shower comfort prediction.

        Args:
            ts: ISO timestamp
            predicted_temp: Predicted tap temperature
            comfort_level: Comfort level shown to user (Cold, Luke Warm, Comfortable, Hot)
            feedback: User feedback (thumbs_up or thumbs_down)
        """
        if self.conn is None:
            self.connect()

        cur = self.conn.cursor()
        cur.execute(
            'INSERT INTO shower_feedback (ts, predicted_temp, comfort_level, feedback) VALUES (?, ?, ?, ?)',
            (ts, predicted_temp, comfort_level, feedback)
        )
        self.conn.commit()

    def get_shower_feedback(self, limit: int = None):
        """Retrieve shower feedback for analytics.

        Returns list of dicts with keys: ts, predicted_temp, comfort_level, feedback
        """
        if self.conn is None:
            self.connect()

        cur = self.conn.cursor()
        if limit:
            cur.execute(
                'SELECT ts, predicted_temp, comfort_level, feedback FROM shower_feedback ORDER BY ts DESC LIMIT ?',
                (limit,)
            )
        else:
            cur.execute('SELECT ts, predicted_temp, comfort_level, feedback FROM shower_feedback ORDER BY ts DESC')

        rows = cur.fetchall()
        return [
            {'ts': r[0], 'predicted_temp': r[1], 'comfort_level': r[2], 'feedback': r[3]}
            for r in rows
        ]

    @staticmethod
    def _parse_value_and_unit(raw: str):
        """Try to extract a numeric value and unit from a string like '23.4°C' or '0 %'.
        Returns (float or None, unit or None).
        """
        if raw is None:
            return None, None
        if isinstance(raw, (int, float)):
            return float(raw), None
        s = str(raw).strip()
        # split off trailing non-numeric characters
        # handle formats like '23.4 °C', '888.8 °C', '0 %', '38.0 h'
        import re
        m = re.match(r'^([-+]?[0-9]*\.?[0-9]+)\s*(.*)$', s)
        if m:
            try:
                val = float(m.group(1))
            except Exception:
                val = None
            unit = m.group(2).strip() if m.group(2).strip() != '' else None
            return val, unit
        return None, s

    def close(self):
        if self.conn:
            try:
                self.conn.commit()
            except Exception:
                pass
            self.conn.close()
            self.conn = None


def test_db_create():
    # simple smoke test
    db = DBManager(':memory:')
    db.connect()
    db.insert_snapshot('2025-01-01T00:00:00Z', {'dev': {'a': '1.0 V', 'b': '23.5'}})
    cur = db.conn.cursor()
    cur.execute('SELECT COUNT(*) FROM measurements')
    n = cur.fetchone()[0]
    assert n == 2
    db.close()


if __name__ == '__main__':
    test_db_create()
