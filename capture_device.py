#!/usr/bin/env python3
"""Capture periodic raw VBUS data from the device and save to files.

Saves a binary capture every `interval` seconds for `duration` seconds.
By default captures 5 minutes of data in 30s intervals (10 captures).

Usage:
  python3 capture_device.py
  python3 capture_device.py --duration 300 --interval 30 --outdir captures

Files written:
  - <outdir>/capture-<iso-timestamp>.bin  (raw bytes captured)
  - <outdir>/manifest.json                (list of captures and timestamps)
"""

import argparse
import os
import time
import json
from datetime import datetime

import config

DEFAULT_DURATION = 300
DEFAULT_INTERVAL = 30


def connect_lan():
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    sock.connect(config.address)

    # wait for HELLO
    try:
        data = sock.recv(1024)
    except Exception:
        data = b''

    if data.startswith(b'+HELLO'):
        # send password
        try:
            sock.send(("PASS %s\n" % config.vbus_pass).encode('ascii'))
            resp = sock.recv(1024)
        except Exception:
            resp = b''
    return sock


def connect_serial():
    import serial

    ser = serial.Serial(config.port, baudrate=config.baudrate, timeout=1)
    return ser


def read_for(sock_like, seconds=2.0):
    """Read available raw bytes from socket-like object for `seconds`.

    `sock_like` should provide `recv` (for sockets) or `read` (for serial).
    Returns bytes.
    """
    end = time.time() + seconds
    data = bytearray()

    # Try to detect socket vs serial by attribute
    is_socket = hasattr(sock_like, 'recv')

    while time.time() < end:
        try:
            if is_socket:
                sock_like.settimeout(0.5)
                chunk = sock_like.recv(4096)
            else:
                chunk = sock_like.read(4096)
        except Exception:
            chunk = b''

        if not chunk:
            # small sleep to avoid busy loop
            time.sleep(0.1)
            continue
        data.extend(chunk)

    return bytes(data)


def capture_session(duration=DEFAULT_DURATION, interval=DEFAULT_INTERVAL, outdir='captures'):
    os.makedirs(outdir, exist_ok=True)
    samples = []

    # Connect according to config
    if config.connection == 'lan':
        sock = connect_lan()
    elif config.connection == 'serial':
        sock = connect_serial()
    else:
        raise SystemExit('capture_device: config.connection must be "lan" or "serial"')

    try:
        n = max(1, int(duration // interval))
        for i in range(n):
            ts = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
            print(f'[{i+1}/{n}] Capturing at {ts} ...')

            if config.connection == 'lan':
                # request a data snapshot
                try:
                    sock.send(b'DATA\n')
                except Exception:
                    pass

            # read ~2s of data (tunable)
            raw = read_for(sock, seconds=2.0)

            filename = os.path.join(outdir, f'capture-{ts}.bin')
            # sanitize filename (replace ':'), safe for most OSes
            filename = filename.replace(':', '-')

            with open(filename, 'wb') as f:
                f.write(raw)

            samples.append({'file': os.path.basename(filename), 'timestamp': ts, 'size': len(raw)})

            # wait until next interval
            if i < n - 1:
                time.sleep(interval)

    finally:
        # try to close
        try:
            sock.close()
        except Exception:
            pass

    manifest = os.path.join(outdir, 'manifest.json')
    with open(manifest, 'w', encoding='utf-8') as mf:
        json.dump({'created': datetime.utcnow().isoformat() + 'Z', 'samples': samples}, mf, indent=2)

    print(f'Done. Wrote {len(samples)} captures to "{outdir}" and manifest "{manifest}"')


def main():
    p = argparse.ArgumentParser(description='Capture periodic raw VBUS data from device')
    p.add_argument('--duration', type=int, default=DEFAULT_DURATION, help='total seconds to capture (default 300)')
    p.add_argument('--interval', type=int, default=DEFAULT_INTERVAL, help='seconds between captures (default 30)')
    p.add_argument('--outdir', default='captures', help='output directory for captures (default "captures")')

    args = p.parse_args()

    capture_session(duration=args.duration, interval=args.interval, outdir=args.outdir)


if __name__ == '__main__':
    main()
