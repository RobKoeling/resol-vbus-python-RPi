# Issues Log

This file documents issues encountered and their solutions.

---

## 2025-11-23: Collector daemon not writing to database

### Symptoms
- Database file (`data/resol_data.db`) not being updated
- `systemctl status resol-collector` shows service is "active (running)"
- No recent entries in snapshots table
- No errors in `journalctl -u resol-collector`

### Diagnosis
1. Checked serial port: `ls -la /dev/ttyACM*` - OK
2. Tested manual read: `python3 resol.py` - returned data OK
3. Ran collector manually: `python3 collector.py --db data/resol_data.db --interval 5` - worked!
4. Compared running process vs service file - **`--interval 5` parameter was missing**

### Root Cause
The systemd service file in `/etc/systemd/system/resol-collector.service` was out of sync with the updated version in the repo. The running service was using an old version without the `--interval` parameter.

### Solution
```bash
# Copy updated service file to systemd
sudo cp systemd/resol-collector.service /etc/systemd/system/

# Reload systemd configuration
sudo systemctl daemon-reload

# Restart the service
sudo systemctl restart resol-collector

# Verify it's running
systemctl status resol-collector
```

### Prevention
After updating any `.service` file in the repo, always run:
```bash
sudo cp systemd/<service-name>.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart <service-name>
```

### Quick Diagnosis Checklist
If the database stops updating:

1. `systemctl status resol-collector` - is it running?
2. `journalctl -u resol-collector --since "30 min ago"` - any errors?
3. `python3 resol.py` - can we read from the device?
4. `python3 collector.py --db data/resol_data.db --interval 5` - does manual run work?

If manual works but service doesn't → service file out of sync.
