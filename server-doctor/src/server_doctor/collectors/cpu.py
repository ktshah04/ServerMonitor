from dataclasses import dataclass

import psutil


@dataclass
class ProcessInfo:
    pid: int
    name: str
    cpu_percent: float
    user: str


@dataclass
class CpuMetrics:
    usage_percent: float
    core_count: int
    top_processes: list[ProcessInfo]


def collect(top_n: int = 5) -> CpuMetrics:
    core_count = psutil.cpu_count(logical=True) or 1

    # Prime per-process CPU counters, then measure over 1s interval
    for proc in psutil.process_iter(["cpu_percent"]):
        pass
    usage = psutil.cpu_percent(interval=1)

    procs: list[ProcessInfo] = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "username"]):
        info = proc.info
        if info["cpu_percent"] and info["cpu_percent"] > 0:
            procs.append(
                ProcessInfo(
                    pid=info["pid"],
                    name=info["name"] or "unknown",
                    cpu_percent=info["cpu_percent"],
                    user=info["username"] or "unknown",
                )
            )

    procs.sort(key=lambda p: p.cpu_percent, reverse=True)
    return CpuMetrics(usage_percent=usage, core_count=core_count, top_processes=procs[:top_n])
