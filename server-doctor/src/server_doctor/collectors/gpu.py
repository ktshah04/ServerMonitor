import subprocess
from dataclasses import dataclass


@dataclass
class GpuInfo:
    index: int
    name: str
    utilization_percent: float
    memory_used_mb: float
    memory_total_mb: float
    temperature_c: float

    @property
    def memory_percent(self) -> float:
        if self.memory_total_mb == 0:
            return 0.0
        return (self.memory_used_mb / self.memory_total_mb) * 100

    @property
    def memory_used_gb(self) -> float:
        return self.memory_used_mb / 1024

    @property
    def memory_total_gb(self) -> float:
        return self.memory_total_mb / 1024


@dataclass
class GpuMetrics:
    gpus: list[GpuInfo]
    available: bool


def collect() -> GpuMetrics:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return GpuMetrics(gpus=[], available=False)

        gpus: list[GpuInfo] = []
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 6:
                continue
            gpus.append(
                GpuInfo(
                    index=int(parts[0]),
                    name=parts[1],
                    utilization_percent=float(parts[2]),
                    memory_used_mb=float(parts[3]),
                    memory_total_mb=float(parts[4]),
                    temperature_c=float(parts[5]),
                )
            )
        return GpuMetrics(gpus=gpus, available=len(gpus) > 0)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return GpuMetrics(gpus=[], available=False)
