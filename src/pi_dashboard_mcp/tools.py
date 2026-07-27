"""MCP Tool definitions and handlers."""

from __future__ import annotations

import json
from typing import Any

from mcp.types import Tool, TextContent

from .collector import cache
from .ipc_client import get_screenshot, scroll_containers, switch_mode


def list_tools() -> list[Tool]:
    return [
        Tool(
            name="pi_get_system_status",
            description="获取树莓派系统状态，包括 CPU、温度、内存、磁盘、IP 和 Tailscale 状态",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="pi_get_container_list",
            description="获取 Docker 容器列表及其运行状态",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="pi_get_dashboard_screenshot",
            description="获取当前 Pi Dashboard 面板截图（Base64 PNG）",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="pi_dashboard_switch_mode",
            description="切换 Pi Dashboard 显示模式",
            inputSchema={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["monitor", "console"],
                        "description": "目标模式",
                    }
                },
                "required": ["mode"],
            },
        ),
        Tool(
            name="pi_dashboard_scroll_containers",
            description="在 Pi Dashboard 容器列表中向下滚动一页",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "pi_get_system_status":
        return [TextContent(type="text", text=cache.get_status_json())]

    if name == "pi_get_container_list":
        return [TextContent(type="text", text=cache.get_containers_json())]

    if name == "pi_get_dashboard_screenshot":
        data = await get_screenshot()
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

    if name == "pi_dashboard_switch_mode":
        mode = arguments.get("mode", "monitor")
        data = await switch_mode(mode)
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

    if name == "pi_dashboard_scroll_containers":
        data = await scroll_containers()
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

    return [TextContent(type="text", text=json.dumps({"error": "unknown tool"}))]
