#!/usr/bin/env python3
"""Generate Grafana alert rules from alerts_config.json"""

import json
import yaml

# Load alerts configuration
with open('config/alerts_config.json', 'r') as f:
    alerts_config = json.load(f)

# Store alert rules
alert_rules = []

def create_alert(uid, title, expr, summary, description, for_duration, threshold):
    """Create a Grafana unified alert rule"""
    return {
        "uid": uid,
        "title": title,
        "condition": "C",
        "data": [
            {
                "refId": "A",
                "relativeTimeRange": {"from": 600, "to": 0},
                "datasourceUid": "prometheus",
                "model": {
                    "expr": expr,
                    "interval": "",
                    "refId": "A",
                    "datasource": {"type": "prometheus", "uid": "prometheus"}
                }
            },
            {
                "refId": "B",
                "relativeTimeRange": {"from": 0, "to": 0},
                "datasourceUid": "-100",
                "model": {
                    "datasource": {"type": "__expr__", "uid": "-100"},
                    "expression": "A",
                    "reducer": "last",
                    "refId": "B",
                    "type": "reduce"
                }
            },
            {
                "refId": "C",
                "relativeTimeRange": {"from": 0, "to": 0},
                "datasourceUid": "-100",
                "model": {
                    "datasource": {"type": "__expr__", "uid": "-100"},
                    "conditions": [{
                        "evaluator": {"params": [threshold], "type": "gt"},
                        "operator": {"type": "and"},
                        "query": {"params": ["B"]},
                        "type": "query"
                    }],
                    "expression": "B",
                    "refId": "C",
                    "type": "threshold"
                }
            }
        ],
        "noDataState": "NoData",
        "execErrState": "Alerting",
        "for": for_duration,
        "annotations": {"summary": summary, "description": description},
        "labels": {},
        "isPaused": False
    }

# CPU alert
if alerts_config["cpu_alerts"]["enabled"]:
    cfg = alerts_config["cpu_alerts"]
    alert_rules.append(create_alert(
        uid="cpu-usage-alert",
        title="CPU Usage Alert",
        expr='100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
        summary=f"CPU usage has been above {cfg['threshold_percent']}% for {cfg['sustained_duration']}",
        description=f"CPU usage has exceeded {cfg['threshold_percent']}% for {cfg['sustained_duration']}",
        for_duration=cfg["sustained_duration"],
        threshold=cfg["threshold_percent"]
    ))

# Memory alert
if alerts_config["memory_alerts"]["enabled"]:
    cfg = alerts_config["memory_alerts"]
    alert_rules.append(create_alert(
        uid="memory-usage-alert",
        title="Memory Usage Alert",
        expr='100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))',
        summary=f"Memory usage is at {cfg['threshold_percent']}% (threshold: {cfg['threshold_percent']}%)",
        description=f"Memory usage has exceeded {cfg['threshold_percent']}% for {cfg['sustained_duration']}",
        for_duration=cfg["sustained_duration"],
        threshold=cfg["threshold_percent"]
    ))

# Storage alert - single dynamic alert for all physical drives
if alerts_config["storage_alerts"]["enabled"]:
    cfg = alerts_config["storage_alerts"]
    # Matches: /rootfs, /rootfs/home, /rootfs/mnt/data[0-9]+
    # Excludes: network mounts, tmpfs, other system paths
    storage_expr = '100 * (1 - (node_filesystem_avail_bytes{mountpoint=~"^/rootfs$|/rootfs/home$|/rootfs/mnt/data[0-9]+$",fstype!="tmpfs"} / node_filesystem_size_bytes{mountpoint=~"^/rootfs$|/rootfs/home$|/rootfs/mnt/data[0-9]+$",fstype!="tmpfs"}))'

    alert_rules.append(create_alert(
        uid="storage-alert-physical-drives",
        title="Storage Alert - Physical Drives",
        expr=storage_expr,
        summary="Storage alert: drive is above threshold",
        description=f"Physical drive storage has exceeded {cfg['threshold_percent']}%",
        for_duration=cfg["evaluation_interval"],
        threshold=cfg["threshold_percent"]
    ))

# Write alert rules
with open('config/alert_rules.yml', 'w') as f:
    yaml.dump({
        "apiVersion": 1,
        "groups": [{
            "orgId": 1,
            "name": "server_monitoring_alerts",
            "folder": "Server Monitoring",
            "interval": "1m",
            "rules": alert_rules
        }]
    }, f, default_flow_style=False, sort_keys=False)

# Write notification policies
notif_interval = alerts_config["storage_alerts"]["notification_interval"]
with open('config/notification_policies.yml', 'w') as f:
    yaml.dump({
        "apiVersion": 1,
        "policies": [{
            "receiver": "slack-alerts",
            "group_by": ["alertname"],
            "group_wait": "10s",
            "group_interval": notif_interval,
            "repeat_interval": notif_interval
        }]
    }, f, default_flow_style=False, sort_keys=False)

print(f"Generated {len(alert_rules)} alert rules successfully!")
