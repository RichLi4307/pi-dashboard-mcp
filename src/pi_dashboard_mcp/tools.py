"""MCP Tool definitions and handlers."""

from __future__ import annotations

import json
from typing import Any

from mcp.types import ImageContent, TextContent, Tool

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
            description=(
                "获取当前 Pi Dashboard 面板截图（PNG）。"
                "返回一张图片，AstrBot 会将其缓存到临时目录并展示给你。"
                "如果用户要求查看或发送截图，请在获得图片后调用 send_message_to_user，"
                "messages=[{\"type\": \"image\", \"path\": \"<截图缓存路径>\"}]。"
            ),
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
                        "enum": ["monitor", "temp", "cpu", "mem", "disk", "net"],
                        "description": (
                            "目标模式：monitor（监控总览）、temp（温度）、cpu（CPU）、"
                            "mem（内存）、disk（磁盘）、net（网络）"
                        ),
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
        if data.get("status") == "ok" and "data" in data:
            return [
                ImageContent(
                    type="image",
                    data=data["data"],
                    mimeType="image/png",
                ),
                TextContent(
                    type="text",
                    text=(
                        "Pi Dashboard 截图已生成。AstrBot 已将图片缓存到临时目录。"
                        "如果用户要求发送截图，请调用 send_message_to_user，"
                        "messages=[{\"type\": \"image\", \"path\": \"<截图缓存路径>\"}]。"
                    ),
                ),
            ]
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

    if name == "pi_dashboard_switch_mode":
        mode = arguments.get("mode", "monitor")
        data = await switch_mode(mode)
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

    if name == "pi_dashboard_scroll_containers":
        data = await scroll_containers()
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

    return [TextContent(type="text", text=json.dumps({"error": "unknown tool"}))]
