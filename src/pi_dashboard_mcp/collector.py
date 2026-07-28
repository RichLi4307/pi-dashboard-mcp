"""System metrics collector for Pi Dashboard MCP.

This module keeps a small in-memory cache that is refreshed by a background
task. Tool handlers return cached values instead of hitting ``/proc``,
``docker`` and ``tailscale`` on every request, which avoids CPU spikes on the
Pi when AstrBot calls the tools repeatedly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_STATUS_INTERVAL = 3.0
DEFAULT_CONTAINER_INTERVAL = 6.0


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


def read_tailscale_status() -> str:
    out = _run(["tailscale", "status", "--json"], timeout=3.0)
    return "Running" if '"BackendState": "Running"' in out else "Stopped"


def _host_status_via_ipc() -> dict[str, Any]:
    """通过 Unix socket 向宿主机 pi_dashboard 进程查询真实 IP/TS 状态。

    容器内的 hostname/tailscale 只能看到容器网络，因此依赖宿主机 IPC。
    """
    path = os.environ.get(
        "PI_DASHBOARD_SOCKET", "/var/lib/pi-dashboard/pi_dashboard.sock"
    )
    if not os.path.exists(path):
        return {}
    try:
        import socket

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(3.0)
            sock.connect(path)
            sock.sendall(b'{"action": "status"}\n')
            data = b""
            while not data.endswith(b"\n"):
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            resp = json.loads(data.decode("utf-8").strip())
            if resp.get("status") == "ok":
                return resp
    except Exception as exc:
        logger.warning("Host status IPC failed: %s", exc)
    return {}


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


def read_docker_containers() -> list[dict[str, str]]:
    """Return running and stopped containers using the Docker Python SDK.

    The client is created lazily and reused to avoid the import/creation
    overhead on every request.
    """
    try:
        import docker

        client = _docker_client()
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


_docker_client_instance = None


def _docker_client():
    global _docker_client_instance
    if _docker_client_instance is None:
        import docker

        _docker_client_instance = docker.DockerClient(
            base_url="unix:///var/run/docker.sock"
        )
    return _docker_client_instance


class MetricsCache:
    """Async cache refreshed by a background task."""

    def __init__(
        self,
        status_interval: float = DEFAULT_STATUS_INTERVAL,
        container_interval: float = DEFAULT_CONTAINER_INTERVAL,
    ) -> None:
        self.status_interval = status_interval
        self.container_interval = container_interval
        self._status: dict[str, Any] = {}
        self._status_json: str = "{}"
        self._containers: list[dict[str, str]] = []
        self._containers_json: str = "[]"
        self._status_ts = 0.0
        self._containers_ts = 0.0
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._cpu_sampler = CpuSampler()

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())
        logger.info("Metrics cache background loop started")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("Metrics cache background loop stopped")

    async def _loop(self) -> None:
        # Prime CPU sampler so the first published value is real instead of 0.
        self._cpu_sampler.read()
        await asyncio.sleep(0.2)
        await self._refresh_status()
        await self._refresh_containers()

        while not self._stop.is_set():
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self.status_interval
                )
                return
            except asyncio.TimeoutError:
                pass

            try:
                await self._refresh_status()
            except Exception:
                logger.exception("Failed to refresh system status")

            if (
                time.time() - self._containers_ts
                >= self.container_interval
            ):
                try:
                    await self._refresh_containers()
                except Exception:
                    logger.exception("Failed to refresh container list")

    async def _refresh_status(self) -> None:
        loop = asyncio.get_running_loop()
        status = await loop.run_in_executor(None, self._collect_status)
        self._status = status
        self._status_json = json.dumps(status, ensure_ascii=False)
        self._status_ts = time.time()

    def _collect_status(self) -> dict[str, Any]:
        # IP/Tailscale 必须走宿主机 IPC，容器网络/命名空间读不到正确值
        host_status = _host_status_via_ipc()
        return {
            "timestamp": datetime.now().isoformat(),
            "hostname": os.uname().nodename,
            "cpu": self._cpu_sampler.read(),
            "temperature": read_cpu_temp(),
            "memory": read_mem_info(),
            "disk": read_disk_usage(),
            "ips": host_status.get("ips", get_ip_list()),
            "tailscale": host_status.get("tailscale", read_tailscale_status()),
        }

    async def _refresh_containers(self) -> None:
        loop = asyncio.get_running_loop()
        containers = await loop.run_in_executor(None, read_docker_containers)
        self._containers = containers
        self._containers_json = json.dumps(containers, ensure_ascii=False)
        self._containers_ts = time.time()

    def get_status(self) -> dict[str, Any]:
        return self._status

    def get_status_json(self) -> str:
        return self._status_json

    def get_containers(self) -> list[dict[str, str]]:
        return self._containers

    def get_containers_json(self) -> str:
        return self._containers_json


cache = MetricsCache()
