**Systemd service for the collector**

Place the unit file `systemd/resol-collector.service` into `/etc/systemd/system/` and enable it:

1. Copy unit file (run as root or with sudo):

```bash
sudo cp systemd/resol-collector.service /etc/systemd/system/resol-collector.service
```

2. Reload systemd, enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable resol-collector.service
sudo systemctl start resol-collector.service
```

3. Check status and logs:

```bash
sudo systemctl status resol-collector.service
journalctl -u resol-collector.service -f
```

Notes:
- The unit uses `User=pi` and `%h` (home) in paths. Adjust `User` and paths to match your system layout.
- The collector writes DB to `data/resol_data.db` under the repository. Ensure the specified user has write permission to that path.
