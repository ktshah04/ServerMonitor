from unittest.mock import MagicMock, patch

from server_doctor.collectors import cpu, disk, memory


@patch("server_doctor.collectors.cpu.psutil")
def test_cpu_collect(mock_psutil):
    mock_psutil.cpu_percent.return_value = 45.0
    mock_psutil.cpu_count.return_value = 16

    mock_proc = MagicMock()
    mock_proc.info = {"pid": 123, "name": "python", "cpu_percent": 200.0, "username": "kshah"}
    mock_psutil.process_iter.return_value = [mock_proc]

    result = cpu.collect(top_n=3)
    assert result.usage_percent == 45.0
    assert result.core_count == 16
    assert len(result.top_processes) == 1
    assert result.top_processes[0].pid == 123


@patch("server_doctor.collectors.cpu.psutil")
def test_cpu_collect_filters_zero_cpu(mock_psutil):
    mock_psutil.cpu_percent.return_value = 10.0
    mock_psutil.cpu_count.return_value = 4

    idle = MagicMock()
    idle.info = {"pid": 1, "name": "idle", "cpu_percent": 0, "username": "root"}
    active = MagicMock()
    active.info = {"pid": 2, "name": "active", "cpu_percent": 50.0, "username": "kshah"}
    mock_psutil.process_iter.return_value = [idle, active]

    result = cpu.collect(top_n=5)
    assert len(result.top_processes) == 1
    assert result.top_processes[0].name == "active"


@patch("server_doctor.collectors.memory.psutil")
@patch("server_doctor.collectors.memory._parse_oom_kills")
def test_memory_collect(mock_oom, mock_psutil):
    mock_oom.return_value = []
    mock_mem = MagicMock()
    mock_mem.total = 128 * 1024**3
    mock_mem.used = 100 * 1024**3
    mock_mem.available = 28 * 1024**3
    mock_mem.buffers = 2 * 1024**3
    mock_mem.cached = 15 * 1024**3
    mock_mem.shared = 1 * 1024**3
    mock_mem.percent = 78.1
    mock_psutil.virtual_memory.return_value = mock_mem

    mock_proc = MagicMock()
    mem_info = MagicMock()
    mem_info.rss = 40 * 1024**3
    mock_proc.info = {"pid": 555, "name": "train.py", "memory_info": mem_info, "username": "kshah"}
    mock_psutil.process_iter.return_value = [mock_proc]

    result = memory.collect(top_n=3)
    assert result.total_bytes == 128 * 1024**3
    assert result.usage_percent == 78.1
    assert len(result.top_processes) == 1
    assert result.top_processes[0].pid == 555
    assert abs(result.total_gb - 128.0) < 0.1
    assert abs(result.used_gb - 100.0) < 0.1
    assert abs(result.buffers_cached_gb - 17.0) < 0.1
    assert result.process_rss_total_bytes == 40 * 1024**3


@patch("server_doctor.collectors.memory.subprocess.run")
def test_parse_oom_kills_with_data(mock_run):
    mock_run.return_value = MagicMock(
        stdout="[2026-03-10T12:00:00] Killed process 9876 (python) total-vm:12345kB\n",
        returncode=0,
    )
    result = memory._parse_oom_kills()
    assert len(result) == 1
    assert result[0].pid == 9876
    assert result[0].process_name == "python"


@patch("server_doctor.collectors.memory.subprocess.run")
def test_parse_oom_kills_no_kills(mock_run):
    mock_run.return_value = MagicMock(stdout="", returncode=0)
    result = memory._parse_oom_kills()
    assert result == []


@patch("server_doctor.collectors.memory.subprocess.run")
def test_parse_oom_kills_permission_error(mock_run):
    mock_run.side_effect = PermissionError
    result = memory._parse_oom_kills()
    assert result == []


@patch("server_doctor.collectors.disk.psutil")
@patch("server_doctor.collectors.disk._get_docker_disk")
@patch("server_doctor.collectors.disk._scan_top_dirs")
def test_disk_collect(mock_scan, mock_docker, mock_psutil):
    mock_docker.return_value = None
    mock_scan.return_value = []

    part = MagicMock()
    part.mountpoint = "/"
    part.fstype = "ext4"
    part.device = "/dev/sda1"
    mock_psutil.disk_partitions.return_value = [part]

    usage = MagicMock()
    usage.total = 500 * 1024**3
    usage.used = 200 * 1024**3
    usage.free = 300 * 1024**3
    usage.percent = 40.0
    mock_psutil.disk_usage.return_value = usage

    result = disk.collect()
    assert len(result.mounts) == 1
    assert result.mounts[0].mountpoint == "/"
    assert result.mounts[0].usage_percent == 40.0
    assert result.mounts[0].total_human == "500.0 GB"
    assert result.mounts[0].free_human == "300.0 GB"


@patch("server_doctor.collectors.disk.psutil")
@patch("server_doctor.collectors.disk._get_docker_disk")
def test_disk_collect_excludes_tmpfs(mock_docker, mock_psutil):
    mock_docker.return_value = None

    part = MagicMock()
    part.mountpoint = "/dev/shm"
    part.fstype = "tmpfs"
    part.device = "tmpfs"
    mock_psutil.disk_partitions.return_value = [part]

    result = disk.collect()
    assert len(result.mounts) == 0


@patch("server_doctor.collectors.disk.subprocess.run")
def test_scan_top_dirs(mock_run):
    mock_run.return_value = MagicMock(
        stdout="1073741824\t/data/subdir1\n536870912\t/data/subdir2\n1610612736\t/data\n",
        returncode=0,
    )
    result = disk._scan_top_dirs("/data", top_n=5)
    assert len(result) == 2
    assert result[0].path == "/data/subdir1"
    assert result[0].size_bytes == 1073741824


@patch("server_doctor.collectors.disk.subprocess.run")
def test_scan_top_dirs_timeout(mock_run):
    import subprocess

    mock_run.side_effect = subprocess.TimeoutExpired(cmd="du", timeout=30)
    result = disk._scan_top_dirs("/data", top_n=5)
    assert result == []


@patch("server_doctor.collectors.disk.subprocess.run")
def test_get_docker_disk(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="523GB\t89GB (17%)\n100MB\t50MB (50%)\n",
    )
    result = disk._get_docker_disk()
    assert result is not None
    assert result.total_bytes > 0
    assert result.reclaimable_bytes > 0


@patch("server_doctor.collectors.disk.subprocess.run")
def test_get_docker_disk_not_installed(mock_run):
    mock_run.side_effect = FileNotFoundError
    result = disk._get_docker_disk()
    assert result is None
