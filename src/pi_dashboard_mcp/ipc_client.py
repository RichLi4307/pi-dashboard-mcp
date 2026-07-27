"""IPC client to communicate with pi_dashboard process."""

from __future__ import annotations

import json
import logging
import os
import socket

logger = logging.getLogger(__name__)

SOCKET_PATH = os.environ.get(
    "PI_DASHBOARD_SOCKET", "/run/pi_dashboard/pi_dashboard.sock"
)


async def request(action: str, **kwargs) -> dict:
    payload = {"action": action, **kwargs}
    data = json.dumps(payload).encode("utf-8")

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    try:
        sock.connect(SOCKET_PATH)
        sock.sendall(data + b"\n")

        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
            if b"\n" in response:
                break

        return json.loads(response.decode("utf-8").strip())
    except (OSError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("IPC request failed: %s", exc)
        return {"status": "error", "message": str(exc)}
    finally:
        try:
            sock.close()
        except OSError:
            pass


async def get_screenshot() -> dict:
    return await request("screenshot")


async def switch_mode(mode: str) -> dict:
    return await request("switch_mode", mode=mode)


async def scroll_containers() -> dict:
    return await request("scroll_containers")
