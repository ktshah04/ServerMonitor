import json
import time
from unittest.mock import patch

from server_doctor.alerting import CooldownTracker, check_alerts, send_slack
from server_doctor.collectors.cpu import CpuMetrics, ProcessInfo as CpuProcess
from server_doctor.collectors.disk import DiskMetrics, DockerDisk, MountInfo
from server_doctor.collectors.gpu import GpuInfo, GpuMetrics
from server_doctor.collectors.memory import MemoryMetrics, ProcessInfo as MemProcess


def _make_memory(usage_percent: float = 50.0) -> MemoryMetrics:
    return MemoryMetrics(
        total_bytes=256 * 1024**3,
        used_bytes=int(256 * 1024**3 * usage_percent / 100),
        available_bytes=int(256 * 1024**3 * (1 - usage_percent / 100)),
        buffers_bytes=2 * 1024**3,
        cached_bytes=30 * 1024**3,
        shared_bytes=1 * 1024**3,
        usage_percent=usage_percent,
        process_rss_total_bytes=44 * 1024**3,
        top_processes=[
            MemProcess(pid=100, name="python", rss_bytes=40 * 1024**3, user="kshah"),
            MemProcess(pid=200, name="mysqld", rss_bytes=4 * 1024**3, user="mysql"),
        ],
        recent_oom_kills=[],
    )


def _make_cpu(usage_percent: float = 30.0) -> CpuMetrics:
    return CpuMetrics(
        usage_percent=usage_percent,
        core_count=8,
        top_processes=[CpuProcess(pid=100, name="python", cpu_percent=400.0, user="kshah")],
    )


def _make_disk(usage_percent: float = 50.0) -> DiskMetrics:
    return DiskMetrics(
        mounts=[
            MountInfo(
                mountpoint="/",
                total_bytes=500 * 1024**3,
                used_bytes=int(500 * 1024**3 * usage_percent / 100),
                free_bytes=int(500 * 1024**3 * (1 - usage_percent / 100)),
                usage_percent=usage_percent,
                top_directories=[],
            )
        ],
        docker=DockerDisk(total_bytes=100 * 1024**3, reclaimable_bytes=50 * 1024**3),
    )


def _make_gpu(memory_percent: float = 50.0) -> GpuMetrics:
    total_mb = 48000.0
    used_mb = total_mb * memory_percent / 100
    return GpuMetrics(
        gpus=[
            GpuInfo(
                index=0,
                name="A600",
                utilization_percent=78.0,
                memory_used_mb=used_mb,
                memory_total_mb=total_mb,
                temperature_c=65.0,
            )
        ],
        available=True,
    )


def test_no_alerts_when_healthy(config):
    alerts = check_alerts(config, _make_memory(50), _make_cpu(30), _make_disk(50), _make_gpu(50))
    assert alerts == []


def test_memory_warning_alert(config):
    alerts = check_alerts(config, _make_memory(90), _make_cpu(30), _make_disk(50), _make_gpu(50))
    assert len(alerts) == 1
    assert alerts[0].alert_type == "memory"
    assert alerts[0].severity == "warning"
    assert "test-server" in alerts[0].message
    assert "python" in alerts[0].message


def test_memory_critical_alert(config):
    alerts = check_alerts(config, _make_memory(96), _make_cpu(30), _make_disk(50), _make_gpu(50))
    assert len(alerts) == 1
    assert alerts[0].severity == "critical"


def test_cpu_warning_alert(config):
    alerts = check_alerts(config, _make_memory(50), _make_cpu(90), _make_disk(50), _make_gpu(50))
    assert len(alerts) == 1
    assert alerts[0].alert_type == "cpu"
    assert "python" in alerts[0].message


def test_disk_warning_alert(config):
    alerts = check_alerts(config, _make_memory(50), _make_cpu(30), _make_disk(87), _make_gpu(50))
    assert len(alerts) == 1
    assert alerts[0].alert_type == "disk_/"
    assert alerts[0].severity == "warning"


def test_disk_critical_alert(config):
    alerts = check_alerts(config, _make_memory(50), _make_cpu(30), _make_disk(92), _make_gpu(50))
    assert len(alerts) == 1
    assert alerts[0].severity == "critical"


def test_gpu_memory_alert(config):
    alerts = check_alerts(config, _make_memory(50), _make_cpu(30), _make_disk(50), _make_gpu(95))
    assert len(alerts) == 1
    assert alerts[0].alert_type == "gpu_0_memory"


def test_multiple_alerts(config):
    alerts = check_alerts(config, _make_memory(90), _make_cpu(90), _make_disk(92), _make_gpu(95))
    assert len(alerts) == 4


def test_cooldown_tracker(tmp_path):
    tracker = CooldownTracker(str(tmp_path / "cooldown.json"), cooldown_minutes=1)
    assert tracker.should_alert("memory") is True

    tracker.mark_alerted("memory")
    assert tracker.should_alert("memory") is False
    assert tracker.should_alert("cpu") is True


def test_cooldown_tracker_expired(tmp_path):
    state_path = str(tmp_path / "cooldown.json")
    state = {"memory": time.time() - 3600}
    (tmp_path / "cooldown.json").write_text(json.dumps(state))

    tracker = CooldownTracker(state_path, cooldown_minutes=30)
    assert tracker.should_alert("memory") is True


def test_send_slack_no_webhook():
    assert send_slack("", "test") is False


@patch("server_doctor.alerting.requests.post")
def test_send_slack_success(mock_post):
    mock_post.return_value.status_code = 200
    assert send_slack("https://hooks.slack.com/test", "hello") is True
    mock_post.assert_called_once_with("https://hooks.slack.com/test", json={"text": "hello"}, timeout=10)
