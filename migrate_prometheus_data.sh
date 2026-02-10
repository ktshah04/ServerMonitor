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

echo "Backing up Prometheus data from container..."
rm -rf "$BACKUP_DIR"
docker cp "$container_name:/prometheus" "$BACKUP_DIR"
backup_size=$(du -sh "$BACKUP_DIR" | cut -f1)
echo "Backup complete ($backup_size) at $BACKUP_DIR"

echo "Recreating stack with persistent volume..."
docker compose up -d

echo "Stopping Prometheus to copy data onto volume..."
docker compose stop "$SERVICE"

container_name=$(docker compose ps -q "$SERVICE" 2>/dev/null)
container_name=$(docker inspect --format '{{.Name}}' "$container_name" | sed 's|^/||')

echo "Copying backed-up data into new container..."
docker cp "$BACKUP_DIR/." "$container_name:/prometheus"

echo "Starting Prometheus..."
docker compose start "$SERVICE"

echo "Cleaning up backup..."
rm -rf "$BACKUP_DIR"

echo "Migration complete. Prometheus is running with persistent storage and historical data preserved."
