import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from server_doctor.alerting import Alert
from server_doctor.config import Config

logger = logging.getLogger(__name__)


@dataclass
class RemediationResult:
    action: str
    success: bool
    output: str


def run_remediations(config: Config, alerts: list[Alert]) -> list[RemediationResult]:
    results: list[RemediationResult] = []
    enabled = set(config.enabled_remediations)

    has_disk_alert = any(a.alert_type.startswith("disk_") for a in alerts)

    if has_disk_alert and "docker_prune" in enabled:
        results.append(_docker_prune(alerts))

    if has_disk_alert and "log_cleanup" in enabled:
        results.append(_log_cleanup())

    _log_results(config, results)
    return results


def _docker_prune(alerts: list[Alert]) -> RemediationResult:
    is_critical = any(a.severity == "critical" and a.alert_type.startswith("disk_") for a in alerts)

    cmds: list[list[str]] = [["docker", "system", "prune", "-af", "--filter", "until=72h"]]
    if is_critical:
        cmds.append(["docker", "volume", "prune", "-f"])

    outputs: list[str] = []
    success = True
    for cmd in cmds:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            outputs.append(result.stdout.strip())
            if result.returncode != 0:
                outputs.append(f"stderr: {result.stderr.strip()}")
                success = False
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            outputs.append(str(e))
            success = False

    action = "docker_prune" + ("_with_volumes" if is_critical else "")
    return RemediationResult(action=action, success=success, output="\n".join(outputs))


def _log_cleanup() -> RemediationResult:
    try:
        result = subprocess.run(
            ["journalctl", "--vacuum-size=500M"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return RemediationResult(
            action="log_cleanup",
            success=result.returncode == 0,
            output=result.stdout.strip() or result.stderr.strip(),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return RemediationResult(action="log_cleanup", success=False, output=str(e))


def _log_results(config: Config, results: list[RemediationResult]) -> None:
    log_path = Path(config.remediation_log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(log_path)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    file_logger = logging.getLogger("server_doctor.remediation.file")
    file_logger.addHandler(handler)
    file_logger.setLevel(logging.INFO)

    for r in results:
        level = logging.INFO if r.success else logging.ERROR
        file_logger.log(level, "action=%s success=%s output=%s", r.action, r.success, r.output[:500])

    file_logger.removeHandler(handler)
    handler.close()
