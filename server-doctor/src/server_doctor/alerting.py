import json
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from server_doctor.collectors.cpu import CpuMetrics
from server_doctor.collectors.disk import DiskMetrics, MountInfo
from server_doctor.collectors.gpu import GpuMetrics
from server_doctor.collectors.memory import MemoryMetrics
from server_doctor.config import Config


@dataclass
class Alert:
    alert_type: str
    severity: str
    message: str


def check_alerts(
    config: Config,
    memory: MemoryMetrics,
    cpu: CpuMetrics,
    disk: DiskMetrics,
    gpu: GpuMetrics,
) -> list[Alert]:
    alerts: list[Alert] = []
    t = config.thresholds

    if memory.usage_percent >= t.memory_critical:
        alerts.append(_memory_alert(config, memory, "critical"))
    elif memory.usage_percent >= t.memory_warning:
        alerts.append(_memory_alert(config, memory, "warning"))

    if cpu.usage_percent >= t.cpu_warning:
        alerts.append(_cpu_alert(config, cpu))

    for mount in disk.mounts:
        if mount.usage_percent >= t.disk_critical:
            alerts.append(_disk_alert(config, mount, disk, "critical"))
        elif mount.usage_percent >= t.disk_warning:
            alerts.append(_disk_alert(config, mount, disk, "warning"))

    for g in gpu.gpus:
        if g.memory_percent >= t.gpu_memory_warning:
            alerts.append(
                Alert(
                    alert_type=f"gpu_{g.index}_memory",
                    severity="warning",
                    message=(
                        f":warning: GPU {g.index} Memory Alert - {config.hostname} ({g.memory_percent:.1f}%)\n\n"
                        f"GPU {g.index} ({g.name}): {g.memory_used_gb:.1f} GB / {g.memory_total_gb:.1f} GB"
                    ),
                )
            )

    return alerts


def _memory_alert(config: Config, mem: MemoryMetrics, severity: str) -> Alert:
    icon = ":rotating_light:" if severity == "critical" else ":warning:"
    lines = [f"{icon} Memory Alert - {config.hostname} ({mem.usage_percent:.1f}%)\n"]
    lines.append("*Top consumers:*")
    for p in mem.top_processes:
        lines.append(f"  PID {p.pid}  `{p.name}`  {p.rss_gb:.1f} GB  (user: {p.user})")
    lines.append(f"\nTotal: {mem.used_gb:.1f} GB used / {mem.total_gb:.1f} GB total")

    if mem.top_processes:
        top = mem.top_processes[0]
        lines.append(f"\nSuggested: kill PID {top.pid} to free ~{top.rss_gb:.1f} GB")
        lines.append(f'  `ssh {config.hostname} "kill {top.pid}"`')

    if mem.recent_oom_kills:
        lines.append(f"\nRecent OOM kills: {len(mem.recent_oom_kills)} found in dmesg")
        for oom in mem.recent_oom_kills[:3]:
            lines.append(f"  PID {oom.pid} ({oom.process_name})")

    return Alert(alert_type="memory", severity=severity, message="\n".join(lines))


def _cpu_alert(config: Config, cpu: CpuMetrics) -> Alert:
    lines = [f":warning: CPU Alert - {config.hostname} ({cpu.usage_percent:.1f}%)\n"]
    lines.append(f"*Top consumers* ({cpu.core_count} cores):")
    for p in cpu.top_processes:
        lines.append(f"  PID {p.pid}  `{p.name}`  {p.cpu_percent:.0f}%  (user: {p.user})")
    return Alert(alert_type="cpu", severity="warning", message="\n".join(lines))


def _disk_alert(config: Config, mount: MountInfo, disk: DiskMetrics, severity: str) -> Alert:
    icon = ":rotating_light:" if severity == "critical" else ":warning:"
    lines = [f"{icon} Disk Alert - {config.hostname} {mount.mountpoint} ({mount.usage_percent:.1f}%)\n"]

    if mount.top_directories:
        lines.append("*Largest directories:*")
        for d in mount.top_directories:
            lines.append(f"  {d.path}    {d.size_human}")

    if disk.docker:
        lines.append(f"\nDocker reclaimable: {disk.docker.reclaimable_human} (unused images/volumes)")
        lines.append(f'  `ssh {config.hostname} "docker system prune -af"`')

    lines.append(f"\n{mount.free_human} free of {mount.total_human}")
    return Alert(alert_type=f"disk_{mount.mountpoint}", severity=severity, message="\n".join(lines))


class CooldownTracker:
    def __init__(self, state_path: str, cooldown_minutes: int) -> None:
        self._path = Path(state_path)
        self._cooldown_seconds = cooldown_minutes * 60
        self._state: dict[str, float] = self._load()

    def _load(self) -> dict[str, float]:
        if self._path.exists():
            return json.loads(self._path.read_text())
        return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._state))

    def should_alert(self, alert_type: str) -> bool:
        last = self._state.get(alert_type, 0)
        return (time.time() - last) >= self._cooldown_seconds

    def mark_alerted(self, alert_type: str) -> None:
        self._state[alert_type] = time.time()
        self._save()


def send_slack(webhook_url: str, message: str) -> bool:
    if not webhook_url:
        return False
    resp = requests.post(webhook_url, json={"text": message}, timeout=10)
    return resp.status_code == 200
