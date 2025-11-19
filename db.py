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
        self.conn.commit()

    def insert_snapshot(self, ts: str, snapshot: Dict[str, Dict[str, str]]):
        """Insert a snapshot into the measurements table.

        snapshot: { device_name: { field_name: value_with_unit_str, ... }, ... }
        The value string is parsed to numeric value and unit when possible.
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

        cur.executemany('INSERT INTO measurements (ts, device, field, value, unit) VALUES (?,?,?,?,?)', rows)
        self.conn.commit()

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
