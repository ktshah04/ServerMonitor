import argparse
import socket
from pathlib import Path

from server_doctor.collectors import cpu, disk, gpu, memory
from server_doctor.config import Config, load_config

WARN = "\033[93m\u26a0\ufe0f\033[0m"
OK = "\033[92m\u2713\033[0m"


def _format_percent(value: float, warning: int, critical: int = 100) -> str:
    if value >= critical:
        return f"\033[91m{value:.1f}%\033[0m  {WARN}"
    if value >= warning:
        return f"\033[93m{value:.1f}%\033[0m  {WARN}"
    return f"\033[92m{value:.1f}%\033[0m"


def _human_bytes(b: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(b) < 1024:
            return f"{b:.1f} {unit}"
        b = int(b / 1024)
    return f"{b:.1f} PB"


def print_health(config: Config) -> None:
    hostname = config.hostname or socket.gethostname()
    t = config.thresholds

    mem = memory.collect(top_n=config.top_n_processes)
    cpu_metrics = cpu.collect(top_n=config.top_n_processes)
    disk_metrics = disk.collect(scan_directories=config.disk_scan_directories, top_n=config.top_n_directories)
    gpu_metrics = gpu.collect()

    width = 55
    print(f"\n\033[1m\u2554\u2550\u2550 {hostname} Health \u2550{'=' * (width - len(hostname) - 12)}\u2557\033[0m")

    print(f"  CPU:    {_format_percent(cpu_metrics.usage_percent, t.cpu_warning)}  ({cpu_metrics.core_count} cores)")
    print(
        f"  Memory: {_format_percent(mem.usage_percent, t.memory_warning, t.memory_critical)}"
        f"  ({mem.used_gb:.1f} GB / {mem.total_gb:.1f} GB)"
    )
    print(f"          Processes: {mem.process_rss_total_gb:.1f} GB  |  Buffers/Cache: {mem.buffers_cached_gb:.1f} GB")

    if gpu_metrics.available:
        for g in gpu_metrics.gpus:
            status = f"{g.utilization_percent:.0f}%" if g.utilization_percent > 0 else "idle"
            vram = f"({g.memory_used_gb:.0f} GB / {g.memory_total_gb:.0f} GB VRAM)"
            print(f"  GPU {g.index}:  {status:6s} {g.name} {vram}")

    print()
    print("  Disks:")
    for m in disk_metrics.mounts:
        pct = _format_percent(m.usage_percent, t.disk_warning, t.disk_critical)
        print(f"    {m.mountpoint:20s} {pct}   ({m.free_human} free)")

    print()
    print("  Top Memory:")
    for p in mem.top_processes:
        print(f"    PID {p.pid:<7d} {p.name:25s} {p.rss_gb:.1f} GB  ({p.user})")

    print()
    print("  Top CPU:")
    for p in cpu_metrics.top_processes:
        print(f"    PID {p.pid:<7d} {p.name:25s} {p.cpu_percent:.0f}%     ({p.user})")

    if disk_metrics.docker:
        d = disk_metrics.docker
        print(f"\n  Docker: {d.total_human} used, {d.reclaimable_human} reclaimable")

    if mem.recent_oom_kills:
        print(f"\n  Recent OOM kills: {len(mem.recent_oom_kills)} in dmesg")
        for oom in mem.recent_oom_kills[:3]:
            print(f"    PID {oom.pid} ({oom.process_name})")

    print(f"\033[1m\u255a{'=' * (width - 1)}\u255d\033[0m\n")


def run_monitor(config: Config) -> None:
    from server_doctor.alerting import Alert, CooldownTracker, check_alerts, send_slack
    from server_doctor.remediation import run_remediations

    mem = memory.collect(top_n=config.top_n_processes)
    cpu_metrics = cpu.collect(top_n=config.top_n_processes)
    disk_metrics = disk.collect(scan_directories=config.disk_scan_directories, top_n=config.top_n_directories)
    gpu_metrics = gpu.collect()

    alerts = check_alerts(config, mem, cpu_metrics, disk_metrics, gpu_metrics)
    if not alerts:
        return

    cooldown = CooldownTracker(config.cooldown_state_path, config.alert_cooldown_minutes)
    sent_alerts: list[Alert] = []

    for alert in alerts:
        if cooldown.should_alert(alert.alert_type):
            if send_slack(config.slack_webhook_url, alert.message):
                cooldown.mark_alerted(alert.alert_type)
                sent_alerts.append(alert)

    if sent_alerts:
        run_remediations(config, sent_alerts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Server health diagnostics and alerting")
    parser.add_argument("command", nargs="?", default="health", choices=["health", "monitor"])
    parser.add_argument("--config", "-c", type=Path, help="Path to config file")
    args = parser.parse_args()

    config_path = args.config
    if config_path:
        config = load_config(config_path)
    else:
        from server_doctor.config import DEFAULT_CONFIG_PATH

        if DEFAULT_CONFIG_PATH.exists():
            config = load_config(DEFAULT_CONFIG_PATH)
        else:
            config = Config()

    if args.command == "monitor":
        run_monitor(config)
    else:
        print_health(config)


if __name__ == "__main__":
    main()
