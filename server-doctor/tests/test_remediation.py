from unittest.mock import MagicMock, patch

from server_doctor.alerting import Alert
from server_doctor.remediation import run_remediations


def test_no_remediation_without_disk_alert(config):
    alerts = [Alert(alert_type="memory", severity="warning", message="high memory")]
    results = run_remediations(config, alerts)
    assert results == []


@patch("server_doctor.remediation.subprocess.run")
def test_docker_prune_on_disk_warning(mock_run, config):
    mock_run.return_value = MagicMock(returncode=0, stdout="Deleted images", stderr="")
    alerts = [Alert(alert_type="disk_/", severity="warning", message="disk full")]
    results = run_remediations(config, alerts)
    assert len(results) >= 1
    docker_results = [r for r in results if r.action.startswith("docker_prune")]
    assert len(docker_results) == 1
    assert docker_results[0].success is True
    assert docker_results[0].action == "docker_prune"


@patch("server_doctor.remediation.subprocess.run")
def test_docker_volume_prune_on_critical(mock_run, config):
    mock_run.return_value = MagicMock(returncode=0, stdout="Pruned", stderr="")
    alerts = [Alert(alert_type="disk_/mnt/data1", severity="critical", message="disk critical")]
    results = run_remediations(config, alerts)
    docker_results = [r for r in results if r.action.startswith("docker_prune")]
    assert len(docker_results) == 1
    assert docker_results[0].action == "docker_prune_with_volumes"


@patch("server_doctor.remediation.subprocess.run")
def test_remediation_handles_failure(mock_run, config):
    mock_run.side_effect = FileNotFoundError("docker not found")
    alerts = [Alert(alert_type="disk_/", severity="warning", message="disk full")]
    results = run_remediations(config, alerts)
    failed = [r for r in results if not r.success]
    assert len(failed) >= 1


def test_disabled_remediation(config):
    config.enabled_remediations = []
    alerts = [Alert(alert_type="disk_/", severity="warning", message="disk full")]
    results = run_remediations(config, alerts)
    assert results == []
