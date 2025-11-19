#!/usr/bin/env python3
"""Run the Flask UI and print accessible network address information.

This helper attempts to determine a suitable LAN IP address for the
Raspberry Pi (by opening a UDP socket to a public address) and prints
one or more URLs you can point your laptop browser at. It then starts
the Flask development server listening on 0.0.0.0.
"""

import socket
import sys
import importlib.util
from pathlib import Path
import sys

# Ensure the repository root is on sys.path so local modules (like `db`)
# can be imported when running this script directly from the repo root.
repo_root = str(Path(__file__).parent.parent.resolve())
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Load the `app` object from the sibling `app.py` module without requiring
# the `ui` directory to be a Python package. This allows running
# `python3 ui/run_server.py` directly from the repository root.
spec = importlib.util.spec_from_file_location('ui_app', str(Path(__file__).parent / 'app.py'))
ui_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui_app)
app = ui_app.app


def get_primary_ip():
    """Return the primary LAN IP address or None if unknown."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # doesn't actually send data; used to determine outbound interface
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def print_access_info(host_ip, port=5000):
    print('Flask UI will listen on 0.0.0.0 (all interfaces)')
    if host_ip:
        print(f'Accessible on this LAN IP: http://{host_ip}:{port}/')
        try:
            # also try .local hostname which works if mDNS/Avahi is available
            host = socket.gethostname()
            print(f'Or via mDNS (if available): http://{host}.local:{port}/')
        except Exception:
            pass
    else:
        print('Could not automatically determine a LAN IP address.')
        print('If running on the Pi, open the terminal and run `hostname -I` to discover the IP.')


if __name__ == '__main__':
    port = 5000
    ip = get_primary_ip()
    print_access_info(ip, port=port)
    try:
        # bind to all interfaces so remote browsers can connect
        app.run(host='0.0.0.0', port=port, debug=True)
    except Exception as e:
        print('Failed to start Flask server:', e, file=sys.stderr)
        sys.exit(1)
