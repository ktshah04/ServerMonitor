# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ServerMonitor is a Docker Compose-based server monitoring stack using Prometheus, Node Exporter, and Grafana. It provides a dynamic dashboard for CPU, memory, network, disk I/O, and storage metrics with Slack alerting.

## Architecture

The system has two layers: **runtime** (Docker containers) and **code generation** (Python script that produces Grafana config).

### Runtime Stack (docker-compose.yaml)
- **Node Exporter** - scrapes host system metrics, exposes on internal network
- **DCGM Exporter** - exposes NVIDIA GPU metrics (utilization, memory, temperature) on port 9400; fails gracefully on non-GPU servers
- **Prometheus** - collects metrics from Node Exporter, stores in TSDB with 30-day retention on a named volume (`prometheus_data`)
- **Grafana** - visualizes metrics, provisions dashboards/alerts/datasources from `config/` files mounted as volumes

All containers communicate on a `monitoring` bridge network. Only Grafana exposes a port to the host.

### Alert Generation Pipeline
`generate_alerts.py` reads `config/alerts_config.json` and produces two auto-generated files:
- `config/alert_rules.yml` - Grafana unified alerting rules
- `config/notification_policies.yml` - notification routing/timing per alert type

Alert types have separate Slack contact points defined in `config/alerting.yml`: `system` (CPU/memory), `storage`, and `storage_projection`.

### Key Config Files
| File | Purpose | Auto-generated? |
|------|---------|-----------------|
| `config/alerts_config.json` | Alert thresholds and intervals (source of truth) | No |
| `config/alert_rules.yml` | Grafana alert rules | Yes |
| `config/notification_policies.yml` | Notification routing | Yes |
| `config/alerting.yml` | Slack contact points | No |
| `config/prometheus.yml` | Prometheus scrape targets | No |
| `config/datasources.yml` | Grafana datasource config | No |
| `config/dashboard.yml` | Grafana dashboard provider | No |
| `config/dashboard_dynamic.json` | The actual Grafana dashboard | No |

## Common Commands

```bash
# Generate alert rules after editing alerts_config.json
python3 generate_alerts.py

# Start/restart the stack
docker compose up -d
docker compose restart grafana    # after regenerating alerts

# Migrate Prometheus data to persistent volume
bash migrate_prometheus_data.sh
```

## Environment

Configured via `.env` file (gitignored). Required variables: `NODE_EXPORTER_CONTAINER`, `NODE_EXPORTER_PORT`, `PROMETHEUS_CONTAINER`, `PROMETHEUS_PORT`, `GRAFANA_CONTAINER`, `GRAFANA_PORT`, `GRAFANA_ROOT_URL`, `SLACK_WEBHOOK_URL`.

## Important Details

- `config/prometheus.yml` hardcodes container names (Docker DNS) and a `hostname` label — doesn't use env vars since Prometheus doesn't support them natively.
- Storage alerts use mountpoint regex matching `/rootfs`, `/rootfs/home`, `/rootfs/mnt/data[0-9]+` because Node Exporter mounts the host root at `/rootfs`.
- The `notification_interval` in alerts_config.json is adjusted by subtracting `check_interval` to compute the actual Grafana `repeat_interval` (see `repeat_interval_for()` in generate_alerts.py).
- Dashboard is fully dynamic and doesn't need regeneration when drives change. Only alerts need regeneration.
- GPU monitoring auto-detects: the `has_gpus` template variable queries `DCGM_FI_DEV_GPU_UTIL` — if no DCGM metrics exist, the GPU row and all its panels are hidden. DCGM Exporter requires NVIDIA Container Toolkit on the host.
