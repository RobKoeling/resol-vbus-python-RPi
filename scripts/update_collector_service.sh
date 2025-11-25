# 1. Copy the updated service file to systemd
  sudo cp ~/resol-vbus-python-RPi/systemd/resol-collector.service /etc/systemd/system/

  # 2. Reload systemd to pick up the changes
  sudo systemctl daemon-reload

  # 3. Restart the collector service
  sudo systemctl restart resol-collector

  # 4. Check it's running with the new interval
  sudo systemctl status resol-collector
