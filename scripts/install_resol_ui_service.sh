#!/usr/bin/env bash
# Install the resol-ui.service systemd unit by filling in the current user and working directory.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SCRIPT_DIR%/scripts}"

TEMPLATE="$REPO_ROOT/systemd/resol-ui.service.template"
TARGET="/etc/systemd/system/resol-ui.service"

if [[ ! -f "$TEMPLATE" ]]; then
  echo "Template not found: $TEMPLATE" >&2
  exit 2
fi

USER_NAME="$(whoami)"
WORKDIR="$REPO_ROOT"

echo "Installing resol-ui.service as user='$USER_NAME' workingdir='$WORKDIR'"

tmpfile=$(mktemp)
trap 'rm -f "$tmpfile"' EXIT

# Replace placeholders
sed \
  -e "s|USER_PLACEHOLDER|$USER_NAME|g" \
  -e "s|WORKDIR_PLACEHOLDER|$WORKDIR|g" \
  "$TEMPLATE" > "$tmpfile"

echo "Copying unit to $TARGET (requires sudo)..."
sudo cp "$tmpfile" "$TARGET"
sudo chmod 644 "$TARGET"

echo "Reloading systemd and enabling service..."
sudo systemctl daemon-reload
sudo systemctl enable --now resol-ui.service

echo "Installation complete. Check status with: sudo systemctl status resol-ui.service"
