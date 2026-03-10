import pytest

from server_doctor.config import Config, Thresholds


@pytest.fixture
def config(tmp_path):
    return Config(
        hostname="test-server",
        slack_webhook_url="https://hooks.slack.com/test",
        thresholds=Thresholds(),
        alert_cooldown_minutes=30,
        disk_scan_directories=["/tmp"],
        enabled_remediations=["docker_prune", "log_cleanup"],
        top_n_processes=3,
        top_n_directories=3,
        remediation_log_path=str(tmp_path / "remediation.log"),
        cooldown_state_path=str(tmp_path / "cooldown.json"),
    )
