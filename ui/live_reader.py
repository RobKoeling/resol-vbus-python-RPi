#!/usr/bin/env python3
"""Background live serial reader.

Starts a background thread that periodically attempts to read a short
sample from the configured serial device and parses it using `parser`.
The latest successful parsed snapshot is kept in a small in-memory cache
and can be retrieved with `get_cached_snapshot()`.

This module is intentionally simple and defensive: failures to access the
device are logged to stderr but do not raise exceptions.
"""

import threading
import time
from datetime import datetime
import traceback
from pathlib import Path

_cache = None
_cache_lock = threading.Lock()
_stop_event = threading.Event()
_thread = None


def _set_cache(snapshot):
    global _cache
    with _cache_lock:
        _cache = snapshot


def get_cached_snapshot():
    """Return the latest cached snapshot or None."""
    with _cache_lock:
        return _cache


def _reader_loop(poll_interval=5.0, read_seconds=2.0):
    from capture_device import connect_serial, read_for
    import parser as _parser
    while not _stop_event.is_set():
        try:
            sock = None
            try:
                sock = connect_serial()
                raw = read_for(sock, seconds=read_seconds)
            finally:
                try:
                    if sock is not None:
                        sock.close()
                except Exception:
                    pass

            if raw:
                try:
                    parsed = _parser.parse_raw_bytes(raw)
                except Exception:
                    parsed = None
                if parsed:
                    snap = {'ts': datetime.utcnow().isoformat() + 'Z', 'data': parsed, 'source': 'live'}
                    _set_cache(snap)
        except Exception:
            # Do not crash the thread; log and continue
            traceback.print_exc()

        # Sleep for poll interval, but wake early if stop is requested
        for _ in range(int(max(1, poll_interval))):
            if _stop_event.wait(1.0):
                break


def start(poll_interval=5.0, read_seconds=2.0):
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_reader_loop, args=(poll_interval, read_seconds), daemon=True)
    _thread.start()


def stop(timeout=1.0):
    _stop_event.set()
    global _thread
    if _thread:
        _thread.join(timeout)
        _thread = None


# Optionally start on import if running on the Pi (but keep conservative defaults).
try:
    # If this module is imported, start a background reader with modest defaults.
    start(poll_interval=5.0, read_seconds=2.0)
except Exception:
    pass
