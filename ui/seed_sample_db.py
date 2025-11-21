#!/usr/bin/env python3
"""Create a sample `data/resol_data.db` containing one snapshot for the UI demo."""

from datetime import datetime
import os
import json

from db import DBManager


def main():
    repo_root = os.path.dirname(os.path.dirname(__file__))
    data_dir = os.path.join(repo_root, 'data')
    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, 'resol_data.db')

    manager = DBManager(path=db_path)
    manager.connect()

    ts = datetime.utcnow().isoformat() + 'Z'
    snapshot = {
        'DemoDevice': {
            'Temp. Sensor 1': '25.3 °C',
            'Temp. Sensor 2': '45.8 °C',
            'Temp. Sensor 3': '55.2 °C',
            'Pump Speed Relay 1': '1'
        }
    }

    manager.insert_snapshot(ts, snapshot)
    manager.close()

    print(f'Wrote sample snapshot to {db_path}')


if __name__ == '__main__':
    main()
