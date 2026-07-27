"""System metrics collector for Pi Dashboard MCP."""

from __future__ import annotations

import logging
import os
import subprocess
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def _run(args: list[str], timeout: float = 5.0) -> str:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("Command %s failed: %s", args, exc)
        return ""


def read_cpu_temp() -> str:
    try:
        with open("/host/sys/class/thermal/thermal_zone0/temp", "r") as fh:
            raw = fh.read().strip()
        return f"{int(raw) / 1000:.0f}C"
    except (OSError, ValueError) as exc:
        logger.debug("CPU temp read failed: %s", exc)
        return "N/A"


def read_mem_info() -> dict[str, Any]:
    try:
        mi: dict[str, int] = {}
        with open("/host/proc/meminfo", "r") as fh:
            for line in fh:
                if ":" not in line:
                    continue
                key, val = line.split(":", 1)
                try:
                    mi[key.strip()] = int(val.strip().split()[0])
                except (ValueError, IndexError):
                    continue
        total = mi.get("MemTotal", 0)
        available = mi.get("MemAvailable", mi.get("MemFree", 0))
        used = total - available
        return {
            "total_kb": total,
            "available_kb": available,
            "used_kb": used,
            "used_percent": round(100.0 * used / total, 1) if total else 0.0,
        }
    except OSError as exc:
        logger.debug("Mem info read failed: %s", exc)
        return {}


def read_disk_usage() -> dict[str, float]:
    try:
        st = os.statvfs("/")
        total = st.f_blocks
        free = st.f_bfree
        if total == 0:
            return {}
        return {
            "total_blocks": total,
            "free_blocks": free,
            "used_percent": round(100.0 * (1.0 - free / total), 1),
        }
    except OSError as exc:
        logger.debug("Disk stat failed: %s", exc)
        return {}


def read_docker_containers() -> list[dict[str, str]]:
    try:
        import docker

        client = docker.DockerClient(base_url="unix:///var/run/docker.sock")
        containers: list[dict[str, str]] = []
        for c in client.containers.list(all=True):
            status = c.status
            state = c.attrs.get("State", {}).get("Status", status)
            containers.append(
                {
                    "name": c.name[:18],
                    "status": status[:40],
                    "state": state,
                }
            )
        return containers
    except Exception as exc:
        logger.warning("Docker container query failed: %s", exc)
        return []


def read_tailscale_status() -> str:
    out = _run(["tailscale", "status", "--json"], timeout=3.0)
    return "Running" if '"BackendState": "Running"' in out else "Stopped"


def get_ip_list() -> list[str]:
    out = _run(["hostname", "-I"])
    if not out:
        return []
    ips = [ip for ip in out.split() if not ip.startswith("127.")]
    return [ip for ip in ips if ip.startswith(("192.", "10.", "100."))]


class CpuSampler:
    def __init__(self) -> None:
        self._prev: dict[str, tuple[int, int]] | None = None
        self._history: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=5))

    def read(self) -> dict[str, float]:
        curr = self._sample()
        if not curr:
            return {}
        if self._prev is None:
            self._prev = curr
            return {core: 0.0 for core in curr}

        result: dict[str, float] = {}
        for core, (total, idle) in curr.items():
            if core not in self._prev:
                result[core] = 0.0
                continue
            prev_total, prev_idle = self._prev[core]
            total_diff = total - prev_total
            idle_diff = idle - prev_idle
            if total_diff > 0:
                usage = 100.0 * (1.0 - idle_diff / total_diff)
                usage = max(0.0, min(100.0, usage))
            else:
                usage = 0.0
            self._history[core].append(usage)
            result[core] = round(
                sum(self._history[core]) / len(self._history[core]), 1
            )

        self._prev = curr
        return result

    @staticmethod
    def _sample() -> dict[str, tuple[int, int]]:
        stats: dict[str, tuple[int, int]] = {}
        try:
            with open("/host/proc/stat", "r") as fh:
                for line in fh:
                    if not line.startswith("cpu"):
                        break
                    parts = line.split()
                    if len(parts) < 5:
                        continue
                    core = parts[0]
                    if core != "cpu" and not (
                        core.startswith("cpu") and core[3:].isdigit()
                    ):
                        continue
                    values = [int(v) for v in parts[1:]]
                    total = sum(values)
                    idle = values[3] + values[4]
                    stats[core] = (total, idle)
        except (OSError, ValueError, IndexError) as exc:
            logger.debug("CPU stat read failed: %s", exc)
        return stats


_cpu_sampler = CpuSampler()


def get_system_status() -> dict[str, Any]:
    # The sampler needs two samples to compute usage. Prime it and, if this
    # is the first call, wait a short interval before reading the real value.
    first = _cpu_sampler.read()
    if first and all(v == 0.0 for v in first.values()):
        time.sleep(0.2)
        cpu = _cpu_sampler.read()
    else:
        cpu = first

    return {
        "timestamp": datetime.now().isoformat(),
        "hostname": os.uname().nodename,
        "cpu": cpu,
        "temperature": read_cpu_temp(),
        "memory": read_mem_info(),
        "disk": read_disk_usage(),
        "ips": get_ip_list(),
        "tailscale": read_tailscale_status(),
    }
