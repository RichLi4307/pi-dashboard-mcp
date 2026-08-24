"""MCP Tool definitions and handlers."""

from __future__ import annotations

import json
import os
from typing import Any

from mcp.types import ImageContent, TextContent, Tool

from .collector import cache
from .ipc_client import get_screenshot, scroll_containers, switch_mode
from .screenshot_store import (
    cleanup_screenshots_async,
    save_screenshot_async,
)


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
                "截图会持久化保存，并可通过 URL 访问。"
                "返回一张图片及访问 URL；如需要发送给用户，"
                "可调用 send_message_to_user(messages=[{\"type\": \"image\", \"url\": \"<截图URL>\"}])，"
                "或直接告诉用户截图 URL。"
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="pi_dashboard_cleanup_screenshots",
            description=(
                "清理历史保存的 Pi Dashboard 截图，释放磁盘空间。"
                "可指定保留最近多少张，或删除超过多少小时的旧截图。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "max_age_hours": {
                        "type": "number",
                        "description": "删除超过该小时数的截图。默认 24 小时。设为 0 或负数表示不按时长清理。",
                        "default": 24,
                    },
                    "keep_count": {
                        "type": "integer",
                        "description": "保留最近多少张截图，超出部分删除。默认保留 100 张。设为 0 表示不限制数量。",
                        "default": 100,
                    },
                },
            },
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
            stored = await save_screenshot_async(data["data"])
            internal_url = (
                f"http://pi-dashboard-mcp:{os.environ.get('MCP_PORT', '18473')}"
                f"{stored['url_path']}"
            )
            text = (
                "Pi Dashboard 截图已生成并持久化。"
                f"文件名：{stored['filename']}，大小：{stored['size_bytes']} 字节，"
                f"保存时间：{stored['saved_at']}。"
                f"内部访问 URL：{internal_url}。"
                "如需要发送给用户，可调用 send_message_to_user，"
                f"messages=[{{\"type\": \"image\", \"url\": \"{internal_url}\"}}]。"
            )
            return [
                ImageContent(
                    type="image",
                    data=data["data"],
                    mimeType="image/png",
                ),
                TextContent(type="text", text=text),
            ]
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

    if name == "pi_dashboard_switch_mode":
        mode = arguments.get("mode", "monitor")
        data = await switch_mode(mode)
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

    if name == "pi_dashboard_scroll_containers":
        data = await scroll_containers()
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

    if name == "pi_dashboard_cleanup_screenshots":
        max_age_hours = arguments.get("max_age_hours", 24)
        keep_count = arguments.get("keep_count", 100)
        # Convert negative or zero values to None to disable that cleanup mode.
        max_age_hours = float(max_age_hours) if max_age_hours is not None and max_age_hours > 0 else None
        keep_count = int(keep_count) if keep_count is not None and keep_count > 0 else None
        result = await cleanup_screenshots_async(
            max_age_hours=max_age_hours,
            keep_count=keep_count,
        )
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    return [TextContent(type="text", text=json.dumps({"error": "unknown tool"}))]
