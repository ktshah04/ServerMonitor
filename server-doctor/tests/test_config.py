from pathlib import Path

import pytest
import yaml

from server_doctor.config import Config, Thresholds, load_config


def test_default_config():
    cfg = Config()
    assert cfg.thresholds.memory_warning == 85
    assert cfg.thresholds.memory_critical == 95
    assert cfg.alert_cooldown_minutes == 30
    assert "docker_prune" in cfg.enabled_remediations


def test_load_config_from_yaml(tmp_path):
    config_data = {
        "hostname": "test-host",
        "slack_webhook_url": "https://hooks.slack.com/test",
        "thresholds": {"memory_warning": 80, "memory_critical": 90, "disk_warning": 75},
        "alert_cooldown_minutes": 15,
        "disk_scan_directories": ["/data"],
        "enabled_remediations": ["docker_prune"],
        "top_n_processes": 10,
        "top_n_directories": 3,
        "remediation_log_path": "/tmp/test.log",
        "cooldown_state_path": "/tmp/test.json",
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(config_data))

    cfg = load_config(path)
    assert cfg.hostname == "test-host"
    assert cfg.thresholds.memory_warning == 80
    assert cfg.thresholds.memory_critical == 90
    assert cfg.thresholds.disk_warning == 75
    assert cfg.thresholds.cpu_warning == 85  # default preserved
    assert cfg.alert_cooldown_minutes == 15


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config(Path("/nonexistent/config.yaml"))


def test_thresholds_defaults():
    t = Thresholds()
    assert t.memory_warning == 85
    assert t.memory_critical == 95
    assert t.cpu_warning == 85
    assert t.disk_warning == 85
    assert t.disk_critical == 90
    assert t.gpu_memory_warning == 90
