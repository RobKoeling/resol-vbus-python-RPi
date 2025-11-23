#!/bin/bash
# Check and optionally start RESOL services
# Usage: ./check_services.sh [--start]

SERVICES=("resol-collector" "resol-ui")
START_MODE=false

if [[ "$1" == "--start" ]]; then
    START_MODE=true
fi

echo "=== RESOL Services Status ==="
echo

all_ok=true

for svc in "${SERVICES[@]}"; do
    status=$(systemctl is-active "$svc" 2>/dev/null)

    if [[ "$status" == "active" ]]; then
        echo "[OK]     $svc is running"
    else
        echo "[FAILED] $svc is not running (status: $status)"
        all_ok=false

        if $START_MODE; then
            echo "         Starting $svc..."
            sudo systemctl start "$svc"
            sleep 2
            new_status=$(systemctl is-active "$svc" 2>/dev/null)
            if [[ "$new_status" == "active" ]]; then
                echo "         [OK] $svc started successfully"
            else
                echo "         [ERROR] Failed to start $svc"
            fi
        fi
    fi
done

echo
echo "=== Detailed Status ==="
for svc in "${SERVICES[@]}"; do
    echo
    echo "--- $svc ---"
    systemctl status "$svc" --no-pager -l 2>/dev/null | head -15
done

echo
if $all_ok; then
    echo "All services are running."
    exit 0
else
    if ! $START_MODE; then
        echo "Some services are not running. Use --start to start them:"
        echo "  ./check_services.sh --start"
    fi
    exit 1
fi
