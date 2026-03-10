from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path("/etc/server-doctor/config.yaml")


@dataclass
class Thresholds:
    memory_warning: int = 85
    memory_critical: int = 95
    cpu_warning: int = 85
    disk_warning: int = 85
    disk_critical: int = 90
    gpu_memory_warning: int = 90


@dataclass
class Config:
    hostname: str = ""
    slack_webhook_url: str = ""
    thresholds: Thresholds = field(default_factory=Thresholds)
    alert_cooldown_minutes: int = 30
    disk_scan_directories: list[str] = field(default_factory=lambda: ["/mnt/data1", "/home", "/var/lib/docker"])
    enabled_remediations: list[str] = field(default_factory=lambda: ["docker_prune", "log_cleanup"])
    top_n_processes: int = 5
    top_n_directories: int = 5
    grafana_url: str = ""
    remediation_log_path: str = "/var/log/server-doctor/remediation.log"
    cooldown_state_path: str = "/var/lib/server-doctor/cooldown.json"


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    raw = yaml.safe_load(path.read_text())

    thresholds = Thresholds(**raw.pop("thresholds", {}))
    return Config(thresholds=thresholds, **raw)
