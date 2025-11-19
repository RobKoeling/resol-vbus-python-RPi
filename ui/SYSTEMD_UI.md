**Systemd Service for Flask UI**

This file explains how to install the provided `systemd/resol-ui.service` unit on a Raspberry Pi so the Flask UI starts at boot.

Steps (run on the Raspberry Pi as root or with `sudo`):

1. Copy the service file to `/etc/systemd/system` and edit it. Update `User` and `WorkingDirectory` to match the account and repository path on your Pi (for example `/home/pi/resol-vbus-python`):

```bash
sudo cp systemd/resol-ui.service /etc/systemd/system/resol-ui.service
sudo nano /etc/systemd/system/resol-ui.service
```

2. (Optional) If you installed Python packages into the user's `~/.local`, ensure the `PATH` in the unit includes that location. The shipped unit already adds `/home/pi/.local/bin` to `PATH` but update the path if your user differs.

3. Reload systemd, enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now resol-ui.service
sudo systemctl status resol-ui.service
```

4. Logs: view with `journalctl -u resol-ui.service -f`.

Notes:
- The unit uses `/usr/bin/env python3 /home/pi/resol-vbus-python/ui/run_server.py` to start the app. Adjust the paths as required.
- `run_server.py` prints the detected LAN IP before starting; use that address from your laptop to open the UI (http://<ip>:5000).
- For production, consider using a WSGI server (Gunicorn) or a reverse proxy and running the service under a dedicated non-root user.
