#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="/etc/server-doctor"
LOG_DIR="/var/log/server-doctor"
STATE_DIR="/var/lib/server-doctor"

echo "=== Installing server-doctor ==="

# Install the package
pip install --break-system-packages "$SCRIPT_DIR" 2>/dev/null || pip install "$SCRIPT_DIR"

# Create directories
mkdir -p "$CONFIG_DIR" "$LOG_DIR" "$STATE_DIR"

# Create default config if it doesn't exist
if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    HOSTNAME=$(hostname)
    cat > "$CONFIG_DIR/config.yaml" <<EOF
hostname: $HOSTNAME
slack_webhook_url: ""
thresholds:
  memory_warning: 85
  memory_critical: 95
  cpu_warning: 85
  disk_warning: 85
  disk_critical: 90
  gpu_memory_warning: 90
alert_cooldown_minutes: 30
disk_scan_directories:
  - /mnt/data1
  - /home
  - /var/lib/docker
enabled_remediations:
  - docker_prune
  - log_cleanup
top_n_processes: 5
top_n_directories: 5
grafana_url: ""
remediation_log_path: /var/log/server-doctor/remediation.log
cooldown_state_path: /var/lib/server-doctor/cooldown.json
EOF
    echo "Created default config at $CONFIG_DIR/config.yaml"
    echo "  -> Edit slack_webhook_url before enabling monitoring"
fi

# Install systemd timer
cat > /etc/systemd/system/server-doctor.service <<EOF
[Unit]
Description=Server Doctor health check and alerting
After=network.target docker.service

[Service]
Type=oneshot
ExecStart=$(which server-doctor) monitor
TimeoutStartSec=120
EOF

cat > /etc/systemd/system/server-doctor.timer <<EOF
[Unit]
Description=Run server-doctor every 60 seconds

[Timer]
OnBootSec=30
OnUnitActiveSec=60
AccuracySec=5

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable server-doctor.timer
systemctl start server-doctor.timer

echo "=== Installation complete ==="
echo "  Config: $CONFIG_DIR/config.yaml"
echo "  Logs:   $LOG_DIR/remediation.log"
echo "  Timer:  systemctl status server-doctor.timer"
echo "  CLI:    server-doctor"
