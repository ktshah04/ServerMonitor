#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/tmp/prometheus_backup"
SAFE_BACKUP_DIR="$HOME/prometheus_backup_safe"
SERVICE="prometheus"
VOLUME_NAME="prometheus_data"
MIN_BACKUP_SIZE_KB=1000

container_id=$(docker compose ps -q "$SERVICE" 2>/dev/null)
if [ -z "$container_id" ]; then
    echo "Error: No running $SERVICE container found."
    echo "Make sure you run this from the ServerMonitor directory with the stack running."
    exit 1
fi

container_name=$(docker inspect --format '{{.Name}}' "$container_id" | sed 's|^/||')
echo "Found container: $container_name"

if [ -d "$BACKUP_DIR" ]; then
    existing_size=$(du -sh "$BACKUP_DIR" | cut -f1)
    echo "Error: Backup already exists at $BACKUP_DIR ($existing_size)."
    echo "If a previous migration failed, you may want to resume manually."
    echo "Remove it with: rm -rf $BACKUP_DIR"
    exit 1
fi

echo "Backing up Prometheus data from container..."
docker cp "$container_name:/prometheus" "$BACKUP_DIR"
backup_size_kb=$(du -sk "$BACKUP_DIR" | cut -f1)
backup_size_human=$(du -sh "$BACKUP_DIR" | cut -f1)
echo "Backup complete ($backup_size_human) at $BACKUP_DIR"

if [ "$backup_size_kb" -lt "$MIN_BACKUP_SIZE_KB" ]; then
    echo "Error: Backup is only ${backup_size_human}. This looks like an empty Prometheus instance."
    echo "Expected at least ${MIN_BACKUP_SIZE_KB}KB of data. Aborting to avoid data loss."
    echo "Backup preserved at $BACKUP_DIR for inspection."
    exit 1
fi

echo "Creating safety backup at $SAFE_BACKUP_DIR..."
cp -a "$BACKUP_DIR" "$SAFE_BACKUP_DIR"
echo "Safety backup created. You must manually delete this after verifying: rm -rf $SAFE_BACKUP_DIR"

echo "Recreating stack with persistent volume..."
docker compose up -d

echo "Stopping Prometheus to copy data onto volume..."
docker compose stop "$SERVICE"

echo "Copying backed-up data into volume and fixing ownership..."
docker run --rm \
    -v "$VOLUME_NAME":/prometheus \
    -v "$BACKUP_DIR":/backup:ro \
    alpine sh -c '
        rm -rf /prometheus/*
        if [ -d /backup/data ] && ([ -d /backup/data/wal ] || [ -d /backup/data/chunks_head ] || ls /backup/data/01K* >/dev/null 2>&1); then
            echo "Found TSDB in data/ subdirectory, relocating to /prometheus/"
            cp -a /backup/data/* /prometheus/
        else
            cp -a /backup/* /prometheus/
        fi
        chown -R 65534:65534 /prometheus
    '

echo "Starting Prometheus..."
docker compose start "$SERVICE"

echo "Verifying Prometheus is healthy..."
sleep 5
if ! docker compose ps "$SERVICE" --format '{{.State}}' | grep -q "running"; then
    echo "Error: Prometheus failed to start. Backup preserved at $BACKUP_DIR"
    echo "Check logs with: docker compose logs $SERVICE"
    exit 1
fi

echo "Cleaning up backup..."
rm -rf "$BACKUP_DIR"

echo "Migration complete. Prometheus is running with persistent storage and historical data preserved."
echo ""
echo "IMPORTANT: Safety backup exists at $SAFE_BACKUP_DIR ($(du -sh "$SAFE_BACKUP_DIR" | cut -f1))"
echo "Once you have verified the dashboard, remove it with: rm -rf $SAFE_BACKUP_DIR"
