from unittest.mock import patch

from server_doctor.cli import print_health, _format_percent, _human_bytes
from server_doctor.collectors.cpu import CpuMetrics, ProcessInfo as CpuProcess
from server_doctor.collectors.disk import DiskMetrics, DockerDisk, MountInfo
from server_doctor.collectors.gpu import GpuInfo, GpuMetrics
from server_doctor.collectors.memory import MemoryMetrics, OomKill, ProcessInfo as MemProcess
from server_doctor.config import Config, Thresholds


def test_format_percent_ok():
    result = _format_percent(50.0, 85, 95)
    assert "50.0%" in result
    assert "\033[92m" in result  # green


def test_format_percent_warning():
    result = _format_percent(87.0, 85, 95)
    assert "87.0%" in result
    assert "\033[93m" in result  # yellow


def test_format_percent_critical():
    result = _format_percent(96.0, 85, 95)
    assert "96.0%" in result
    assert "\033[91m" in result  # red


def test_human_bytes():
    assert "1.0 GB" == _human_bytes(1024**3)
    assert "0.0 B" == _human_bytes(0)


@patch("server_doctor.cli.gpu.collect")
@patch("server_doctor.cli.disk.collect")
@patch("server_doctor.cli.cpu.collect")
@patch("server_doctor.cli.memory.collect")
def test_print_health_output(mock_mem, mock_cpu, mock_disk, mock_gpu, capsys):
    mock_mem.return_value = MemoryMetrics(
        total_bytes=128 * 1024**3,
        used_bytes=100 * 1024**3,
        usage_percent=78.1,
        top_processes=[MemProcess(pid=100, name="python", rss_bytes=40 * 1024**3, user="kshah")],
        recent_oom_kills=[OomKill(pid=999, process_name="oom_victim", timestamp="2026-03-10")],
    )
    mock_cpu.return_value = CpuMetrics(
        usage_percent=34.2,
        core_count=8,
        top_processes=[CpuProcess(pid=100, name="python", cpu_percent=400.0, user="kshah")],
    )
    mock_disk.return_value = DiskMetrics(
        mounts=[
            MountInfo(
                mountpoint="/",
                total_bytes=500 * 1024**3,
                used_bytes=200 * 1024**3,
                free_bytes=300 * 1024**3,
                usage_percent=40.0,
                top_directories=[],
            )
        ],
        docker=DockerDisk(total_bytes=100 * 1024**3, reclaimable_bytes=50 * 1024**3),
    )
    mock_gpu.return_value = GpuMetrics(
        gpus=[
            GpuInfo(
                index=0,
                name="A600",
                utilization_percent=78,
                memory_used_mb=38000,
                memory_total_mb=48000,
                temperature_c=65,
            ),
            GpuInfo(
                index=1, name="A600", utilization_percent=0, memory_used_mb=500, memory_total_mb=48000, temperature_c=42
            ),
        ],
        available=True,
    )

    config = Config(hostname="test-server", thresholds=Thresholds())
    print_health(config)

    output = capsys.readouterr().out
    assert "test-server" in output
    assert "CPU:" in output
    assert "Memory:" in output
    assert "GPU 0:" in output
    assert "GPU 1:" in output
    assert "idle" in output
    assert "python" in output
    assert "Docker:" in output
    assert "OOM kills:" in output


@patch("server_doctor.cli.gpu.collect")
@patch("server_doctor.cli.disk.collect")
@patch("server_doctor.cli.cpu.collect")
@patch("server_doctor.cli.memory.collect")
def test_print_health_no_gpu(mock_mem, mock_cpu, mock_disk, mock_gpu, capsys):
    mock_mem.return_value = MemoryMetrics(
        total_bytes=64 * 1024**3,
        used_bytes=30 * 1024**3,
        usage_percent=46.9,
        top_processes=[],
        recent_oom_kills=[],
    )
    mock_cpu.return_value = CpuMetrics(usage_percent=10.0, core_count=4, top_processes=[])
    mock_disk.return_value = DiskMetrics(
        mounts=[
            MountInfo(
                mountpoint="/",
                total_bytes=100 * 1024**3,
                used_bytes=40 * 1024**3,
                free_bytes=60 * 1024**3,
                usage_percent=40.0,
                top_directories=[],
            )
        ],
        docker=None,
    )
    mock_gpu.return_value = GpuMetrics(gpus=[], available=False)

    config = Config(hostname="no-gpu-server", thresholds=Thresholds())
    print_health(config)

    output = capsys.readouterr().out
    assert "no-gpu-server" in output
    assert "GPU" not in output
    assert "Docker:" not in output
