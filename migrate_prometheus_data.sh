#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/tmp/prometheus_backup"
SERVICE="prometheus"

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
backup_size=$(du -sh "$BACKUP_DIR" | cut -f1)
echo "Backup complete ($backup_size) at $BACKUP_DIR"

echo "Recreating stack with persistent volume..."
docker compose up -d

echo "Stopping Prometheus to copy data onto volume..."
docker compose stop "$SERVICE"

echo "Copying backed-up data into volume and fixing ownership..."
docker run --rm \
    -v prometheus_data:/prometheus \
    -v "$BACKUP_DIR":/backup:ro \
    alpine sh -c "rm -rf /prometheus/* && cp -a /backup/* /prometheus/ && chown -R 65534:65534 /prometheus"

echo "Starting Prometheus..."
docker compose start "$SERVICE"

echo "Cleaning up backup..."
rm -rf "$BACKUP_DIR"

echo "Migration complete. Prometheus is running with persistent storage and historical data preserved."
