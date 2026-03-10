import subprocess
from dataclasses import dataclass

import psutil


@dataclass
class ProcessInfo:
    pid: int
    name: str
    rss_bytes: int
    user: str

    @property
    def rss_gb(self) -> float:
        return self.rss_bytes / (1024**3)


@dataclass
class OomKill:
    pid: int
    process_name: str
    timestamp: str


@dataclass
class MemoryMetrics:
    total_bytes: int
    used_bytes: int
    usage_percent: float
    top_processes: list[ProcessInfo]
    recent_oom_kills: list[OomKill]

    @property
    def total_gb(self) -> float:
        return self.total_bytes / (1024**3)

    @property
    def used_gb(self) -> float:
        return self.used_bytes / (1024**3)


def _parse_oom_kills() -> list[OomKill]:
    try:
        result = subprocess.run(
            ["dmesg", "--time-format=iso", "-l", "err,crit"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        kills: list[OomKill] = []
        for line in result.stdout.splitlines():
            if "Killed process" not in line:
                continue
            parts = line.split("Killed process ", 1)
            if len(parts) < 2:
                continue
            rest = parts[1]
            try:
                pid_str, remainder = rest.split(" ", 1)
                pid = int(pid_str)
            except (ValueError, IndexError):
                continue
            pname = remainder.split("(")[1].split(")")[0] if "(" in remainder else "unknown"
            timestamp = line.split("]")[0].lstrip("[").strip() if "]" in line else parts[0].strip()
            kills.append(OomKill(pid=pid, process_name=pname, timestamp=timestamp))
        return kills
    except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
        return []


def collect(top_n: int = 5) -> MemoryMetrics:
    mem = psutil.virtual_memory()

    procs: list[ProcessInfo] = []
    for proc in psutil.process_iter(["pid", "name", "memory_info", "username"]):
        info = proc.info
        mem_info = info.get("memory_info")
        if mem_info and mem_info.rss > 0:
            procs.append(
                ProcessInfo(
                    pid=info["pid"],
                    name=info["name"] or "unknown",
                    rss_bytes=mem_info.rss,
                    user=info["username"] or "unknown",
                )
            )

    procs.sort(key=lambda p: p.rss_bytes, reverse=True)
    oom_kills = _parse_oom_kills()

    return MemoryMetrics(
        total_bytes=mem.total,
        used_bytes=mem.used,
        usage_percent=mem.percent,
        top_processes=procs[:top_n],
        recent_oom_kills=oom_kills,
    )
