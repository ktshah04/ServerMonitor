import subprocess
from dataclasses import dataclass

import psutil


@dataclass
class DirSize:
    path: str
    size_bytes: int

    @property
    def size_human(self) -> str:
        return _human_bytes(self.size_bytes)


@dataclass
class MountInfo:
    mountpoint: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    usage_percent: float
    top_directories: list[DirSize]

    @property
    def total_human(self) -> str:
        return _human_bytes(self.total_bytes)

    @property
    def free_human(self) -> str:
        return _human_bytes(self.free_bytes)


@dataclass
class DockerDisk:
    total_bytes: int
    reclaimable_bytes: int

    @property
    def total_human(self) -> str:
        return _human_bytes(self.total_bytes)

    @property
    def reclaimable_human(self) -> str:
        return _human_bytes(self.reclaimable_bytes)


@dataclass
class DiskMetrics:
    mounts: list[MountInfo]
    docker: DockerDisk | None


def _human_bytes(b: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(b) < 1024:
            return f"{b:.1f} {unit}"
        b = int(b / 1024)
    return f"{b:.1f} PB"


def _scan_top_dirs(path: str, top_n: int) -> list[DirSize]:
    try:
        result = subprocess.run(
            ["du", "--max-depth=1", "-b", path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        entries: list[DirSize] = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            size_str, dir_path = parts
            if dir_path == path:
                continue
            try:
                entries.append(DirSize(path=dir_path, size_bytes=int(size_str)))
            except ValueError:
                continue
        entries.sort(key=lambda d: d.size_bytes, reverse=True)
        return entries[:top_n]
    except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
        return []


def _get_docker_disk() -> DockerDisk | None:
    try:
        result = subprocess.run(
            ["docker", "system", "df", "--format", "{{.Size}}\t{{.Reclaimable}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None

        total = 0
        reclaimable = 0
        for line in result.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                total += _parse_docker_size(parts[0])
                reclaim_str = parts[1].split("(")[0].strip()
                reclaimable += _parse_docker_size(reclaim_str)
        return DockerDisk(total_bytes=total, reclaimable_bytes=reclaimable)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _parse_docker_size(s: str) -> int:
    s = s.strip()
    if not s or s == "0B":
        return 0
    multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4, "kB": 1000}
    for suffix, mult in sorted(multipliers.items(), key=lambda x: len(x[0]), reverse=True):
        if s.endswith(suffix):
            try:
                return int(float(s[: -len(suffix)].strip()) * mult)
            except ValueError:
                return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


EXCLUDED_FSTYPES = {"tmpfs", "devtmpfs", "squashfs", "overlay", "nsfs", "proc", "sysfs", "cgroup", "cgroup2"}


def collect(scan_directories: list[str] | None = None, top_n: int = 5) -> DiskMetrics:
    mounts: list[MountInfo] = []
    seen_devices: set[str] = set()

    for part in psutil.disk_partitions(all=False):
        if part.fstype in EXCLUDED_FSTYPES:
            continue
        if part.device in seen_devices:
            continue
        seen_devices.add(part.device)

        try:
            usage = psutil.disk_usage(part.mountpoint)
        except PermissionError:
            continue

        top_dirs: list[DirSize] = []
        if scan_directories:
            for scan_dir in scan_directories:
                if scan_dir == part.mountpoint or scan_dir.startswith(part.mountpoint + "/"):
                    top_dirs = _scan_top_dirs(scan_dir, top_n)
                    break

        mounts.append(
            MountInfo(
                mountpoint=part.mountpoint,
                total_bytes=usage.total,
                used_bytes=usage.used,
                free_bytes=usage.free,
                usage_percent=usage.percent,
                top_directories=top_dirs,
            )
        )

    docker = _get_docker_disk()
    return DiskMetrics(mounts=mounts, docker=docker)
