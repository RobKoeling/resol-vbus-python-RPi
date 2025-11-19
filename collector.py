#!/usr/bin/env python3
"""Continuous collector that snapshots parsed values and stores them in SQLite.

Runs an infinite loop: every `interval` seconds it connects to the device,
requests a short data sample, parses it using `parser.parse_raw_bytes`, and
inserts the snapshot into the DB.

Run as:
  python3 collector.py --interval 5 --db data/resol_data.db

The `interval` is in minutes (default 5).
"""

import time
import argparse
from datetime import datetime

import config
from db import DBManager


def capture_once_from_socket(sock_like, read_seconds=2.0):
    """Read raw bytes from a socket-like object for a short window (seconds)."""
    data = bytearray()
    end = time.time() + read_seconds
    is_socket = hasattr(sock_like, 'recv')
    while time.time() < end:
        try:
            if is_socket:
                chunk = sock_like.recv(4096)
            else:
                chunk = sock_like.read(4096)
        except Exception:
            chunk = b''
        if chunk:
            data.extend(chunk)
        else:
            time.sleep(0.1)
    return bytes(data)


def connect_device():
    if config.connection == 'lan':
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect(config.address)
        # try to read initial HELLO
        try:
            sock.recv(1024)
        except Exception:
            pass
        # request stream snapshot
        try:
            sock.send(b'DATA\n')
        except Exception:
            pass
        return sock
    elif config.connection == 'serial':
        import serial
        ser = serial.Serial(config.port, baudrate=config.baudrate, timeout=1)
        return ser
    else:
        raise RuntimeError('collector requires config.connection be "lan" or "serial"')


def run_collector(db_path: str, interval_minutes: int):
    db = DBManager(db_path)
    db.connect()

    from parser import parse_raw_bytes

    print(f'Starting collector: interval={interval_minutes}min db={db_path}')
    try:
        while True:
            ts = datetime.utcnow().isoformat() + 'Z'
            print(f'[{ts}] Capturing snapshot...')
            try:
                dev = connect_device()
                raw = capture_once_from_socket(dev, read_seconds=2.0)
                try:
                    dev.close()
                except Exception:
                    pass
            except Exception as e:
                print('Error connecting to device:', e)
                raw = b''

            parsed = {}
            if raw:
                try:
                    parsed = parse_raw_bytes(raw)
                except Exception as e:
                    print('Error parsing raw capture:', e)

            if parsed:
                db.insert_snapshot(ts, parsed)
                print(f'Inserted {sum(len(v) for v in parsed.values())} measurements')
            else:
                print('No parsed fields from snapshot')

            # Sleep until next interval
            time.sleep(interval_minutes * 60)

    except KeyboardInterrupt:
        print('Collector stopping (KeyboardInterrupt)')
    finally:
        db.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--db', default='data/resol_data.db', help='SQLite DB path')
    p.add_argument('--interval', type=int, default=5, help='Interval in minutes between snapshots (default 5)')
    args = p.parse_args()
    run_collector(args.db, args.interval)


if __name__ == '__main__':
    main()
