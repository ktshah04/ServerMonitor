from unittest.mock import MagicMock, patch

from server_doctor.collectors.disk import _human_bytes, _parse_docker_size
from server_doctor.collectors.gpu import GpuInfo, collect as gpu_collect
from server_doctor.collectors.memory import ProcessInfo


def test_human_bytes():
    assert _human_bytes(0) == "0.0 B"
    assert _human_bytes(1024) == "1.0 KB"
    assert _human_bytes(1024**2) == "1.0 MB"
    assert _human_bytes(1024**3) == "1.0 GB"
    assert _human_bytes(1024**4) == "1.0 TB"


def test_parse_docker_size():
    assert _parse_docker_size("0B") == 0
    assert _parse_docker_size("100MB") == 100 * 1024**2
    assert _parse_docker_size("1.5GB") == int(1.5 * 1024**3)
    assert _parse_docker_size("2TB") == 2 * 1024**4


def test_memory_process_rss_gb():
    p = ProcessInfo(pid=1, name="test", rss_bytes=4 * 1024**3, user="root")
    assert abs(p.rss_gb - 4.0) < 0.01


def test_gpu_info_memory_percent():
    g = GpuInfo(
        index=0, name="A100", utilization_percent=50, memory_used_mb=20000, memory_total_mb=40000, temperature_c=60
    )
    assert g.memory_percent == 50.0
    assert abs(g.memory_used_gb - 19.53) < 0.1
    assert abs(g.memory_total_gb - 39.06) < 0.1


def test_gpu_info_zero_memory():
    g = GpuInfo(index=0, name="A100", utilization_percent=0, memory_used_mb=0, memory_total_mb=0, temperature_c=0)
    assert g.memory_percent == 0.0


@patch("server_doctor.collectors.gpu.subprocess.run")
def test_gpu_collect_no_nvidia_smi(mock_run):
    mock_run.side_effect = FileNotFoundError
    result = gpu_collect()
    assert result.available is False
    assert result.gpus == []


@patch("server_doctor.collectors.gpu.subprocess.run")
def test_gpu_collect_parses_output(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="0, NVIDIA A600, 78, 38000, 48000, 65\n1, NVIDIA A600, 0, 500, 48000, 42\n",
    )
    result = gpu_collect()
    assert result.available is True
    assert len(result.gpus) == 2
    assert result.gpus[0].name == "NVIDIA A600"
    assert result.gpus[0].utilization_percent == 78.0
    assert result.gpus[1].utilization_percent == 0.0
